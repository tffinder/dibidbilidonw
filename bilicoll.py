import asyncio,os
from bilibili_api import favorite_list, video, Credential, HEADERS   
import sqlite3
from datetime import datetime
from bilibili_api.exceptions import StatementException
from time import sleep
import httpx
from tqdm import tqdm
import aiohttp

SESSDATA = ""
BILI_JCT = ""
BUVID3 = ""
FFMPEG_PATH = r"D:\ffmpeg-7.1-full_build\bin\ffmpeg"



async def download_url(url: str, out: str, info: str,title:str):
    # 下载函数
    async with httpx.AsyncClient(headers=HEADERS) as sess:
        resp = await sess.get(url)
        length = resp.headers.get('content-length')
        progress_bar = tqdm(
            total=int(length),
            unit='iB',
            unit_scale=True,
            desc=f'下载中: {title}'
            )
        with open(out, 'wb') as f:
            process = 0
            i = 0
            for chunk in resp.iter_bytes(1024):
                if not chunk:
                    break

                process += len(chunk)
                i += 1
                progress_bar.update(len(chunk))
                #print(f'下载 {info} {process} / {length}')
                #sleep(0.01)
                f.write(chunk)
            progress_bar.close()

async def download_video(bv_id, title):
    # 实例化 Credential 类
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    # 实例化 Video 类
    v = video.Video(bvid=bv_id, credential=credential)
    
    # 获取视频信息
    video_info = await v.get_info()
    
    # 检查是否为多P视频
    if video_info['videos'] > 1:
        print(video_info)
        print(f'发现多P视频：{title}，共 {video_info["videos"]} P')
        # 获取所有分P信息
        pages = await v.get_pages()
        
        # 为每个分P创建文件夹
        video_dir = f"{bv_id}"
        os.makedirs(video_dir, exist_ok=True)
        
        # 下载每一个分P
        for page in pages:
            page_num = page['page']
            page_title = page['part']
            print(f'\n开始下载第 {page_num} P: {page_title}')
            
            # 获取当前分P的下载链接
            download_url_data = await v.get_download_url(page_num - 1)  # 页码从0开始
            detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
            streams = detecter.detect_best_streams()
            
            output_file = os.path.join(video_dir, f"P{page_num}_{page_title}.mp4")
            if os.path.exists(output_file):
                print(f"P{page_num} 已存在，跳过下载")
                continue
                
            # 下载处理
            if detecter.check_flv_stream():
                print('下载 FLV 流')
                temp_file = os.path.join(video_dir, "flv_temp.flv")
                await download_url(streams[0].url, temp_file, "FLV 音视频流", f"P{page_num}_{page_title}")
                # 转换文件格式
                os.system(f'{FFMPEG_PATH} -i {temp_file} "{output_file}"')
                # 删除临时文件
                os.remove(temp_file)
            else:
                print('下载 MP4 流')
                video_temp = os.path.join(video_dir, "video_temp.m4s")
                audio_temp = os.path.join(video_dir, "audio_temp.m4s")
                await download_url(streams[0].url, video_temp, "视频流", f"P{page_num}_{page_title}")
                await download_url(streams[1].url, audio_temp, "音频流", f"P{page_num}_{page_title}")
                # 混流
                os.system(f'{FFMPEG_PATH} -loglevel quiet -i "{video_temp}" -i "{audio_temp}" -vcodec copy -acodec copy "{output_file}"')
                # 删除临时文件
                os.remove(video_temp)
                os.remove(audio_temp)
    else:
        # 单P视频的处理逻辑
        print(f"下载单视频：{bv_id}")
        if os.path.exists(f"{bv_id}.mp4"):
            print(f"{bv_id} 视频已存在")
            return
            
        download_url_data = await v.get_download_url(0)
        detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
        streams = detecter.detect_best_streams()
        
        if detecter.check_flv_stream():
            print('下载 FLV 流')
            await download_url(streams[0].url, "flv_temp.flv", "FLV 音视频流", title)
            # 转换文件格式
            os.system(f'{FFMPEG_PATH} -i flv_temp.flv "{bv_id}.mp4"')
            # 删除临时文件
            os.remove("flv_temp.flv")
        else:
            print('下载 MP4 流')
            await download_url(streams[0].url, "video_temp.m4s", "视频流", title)
            await download_url(streams[1].url, "audio_temp.m4s", "音频流", title)
            # 混流
            os.system(f'{FFMPEG_PATH} -loglevel quiet -i video_temp.m4s -i audio_temp.m4s -vcodec copy -acodec copy "{bv_id}.mp4"')
            # 删除临时文件
            os.remove("video_temp.m4s")
            os.remove("audio_temp.m4s")




async def get_favorite_info(fav_id):
    try:
        # 获取收藏夹信息
        fav = favorite_list.FavoriteList(media_id=fav_id)
        
        # 检查是否为视频收藏夹
        if not fav.is_video_favorite_list():
            print(f"错误：当前收藏夹（ID: {fav_id}）不是视频收藏夹")
            print(f"收藏夹类型: {fav.get_favorite_list_type()}")
            return
        else:
            print(f"收藏夹类型: {fav.get_favorite_list_type()}")
            
        # 创建数据库连接
        conn = sqlite3.connect('bilibili_favorites.db')
        cursor = conn.cursor()
        
        # 创建表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            bv_id TEXT,
            av_id INTEGER,
            url TEXT,
            title TEXT,
            uploader TEXT,
            collection_count INTEGER,
            play_count INTEGER,
            danmaku INTEGER,
            favorite_time TEXT,
            upload_time TEXT,
            fav_title TEXT,
            is_deleted INTEGER
                       
        )
        ''')

        page = 1
        total_videos = 0
        del_count = 0
        while True:
            try:
                # 获取当前页的视频
                videos = await fav.get_content_video(page)
                
                #print(videos['medias'])
                #print(videos.get('data', {}).get('medias'))
                #print(type(videos))
                if not videos['medias']:
                    print(f"当前{page}页没有视频")
                    break
                fav_title = videos['info']['title']
                for item in videos['medias']:
                    try:
                        bv_id = item['bvid']
                        av_id = item['id']
                        url = f"https://www.bilibili.com/video/{bv_id}"
                        title = item['title']
                        uploader = item['upper']['name']
                        collection_count = item['cnt_info']['collect']
                        play_count = item['cnt_info']['play']
                        danmaku = item['cnt_info']['danmaku']
                        # 转换时间戳
                        fav_time = datetime.fromtimestamp(item['fav_time']).strftime('%Y-%m-%d %H:%M:%S')
                        upload_time = datetime.fromtimestamp(item['pubtime']).strftime('%Y-%m-%d %H:%M:%S')
                        # 判断视频是否失效
                        is_deleted = item.get('attr', 0) == 9
                        if is_deleted:
                            print(f"视频 {title} 已失效")
                            del_count += 1
                            print(f"已失效视频：{del_count}")
                            #continue
                        # 保存到数据库
                        #查看数据库是否已经存在
                        cursor.execute('SELECT * FROM favorites where bv_id = ?', (bv_id,))
                        results = cursor.fetchall()
                        if results:
                            
                            print(results)
                            print(f"{bv_id}视频信息已存在")
                            continue
                        else:
                            cursor.execute('''
                            INSERT INTO favorites (bv_id, av_id, url, title, uploader, play_count, favorite_time, upload_time, fav_title, collection_count, danmaku, is_deleted)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (bv_id, av_id, url, title, uploader, play_count, fav_time, upload_time, fav_title, collection_count, danmaku, is_deleted))
                        
                        total_videos += 1
                        print(f"已处理视频信息：{title}")
                        if not os.path.exists(f"{bv_id}.mp4"):
                            print(f"下载视频：{bv_id}")
                            await download_video(bv_id,title)
                            print(f"下载完成：{bv_id}")
                        else:
                            print(f"{bv_id}视频已存在")
                        
                    except Exception as e:
                        print(f"处理{bv_id}视频时出错：{str(e)}")
                        continue
                        
                page += 1
                
            except Exception as e:
                print(f"获取第 {page} 页数据时出错：{str(e)}")
                break
                
        # 提交并关闭数据库连接
        conn.commit()
        conn.close()
        print(f"\n任务完成！共处理 {total_videos} 个视频")
        print(f" {del_count} 个视频已失效")
        
    except Exception as e:
        print(f"发生错误：{str(e)}")
        if 'conn' in locals():
            conn.close()

# 运行主函数
async def main():
    # 这里替换为你的收藏夹ID
    fav_id = "3419492731"
    await get_favorite_info(fav_id)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
    
