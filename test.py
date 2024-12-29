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
            for chunk in resp.iter_bytes(1024):
                if not chunk:
                    break

                process += len(chunk)
                progress_bar.update(len(chunk))
                #print(f'下载 {info} {process} / {length}')
                #sleep(0.01)
                f.write(chunk)


async def download_video(bv_id,title):
    # 实例化 Credential 类
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    # 实例化 Video 类
    v = video.Video(bvid=bv_id, credential=credential)
    # 获取视频下载链接
    download_url_data = await v.get_download_url(0)
    # 解析视频下载信息
    detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
    streams = detecter.detect_best_streams()
    # 有 MP4 流 / FLV 流两种可能
    if detecter.check_flv_stream():
        # FLV 流下载
        print('下载 FLV 流')
        await download_url(streams[0].url, "flv_temp.flv", "FLV 音视频流",title)
        # 转换文件格式
        os.system(f'{FFMPEG_PATH} -i flv_temp.flv video{bv_id}.mp4')
        # 删除临时文件
        os.remove("flv_temp.flv")
    else:
        # MP4 流下载
        print('下载 MP4 流')
        await download_url(streams[0].url, "video_temp.m4s", "视频流",title)
        await download_url(streams[1].url, "audio_temp.m4s", "音频流",title)
        # 混流
        os.system(f'{FFMPEG_PATH} -i video_temp.m4s -i audio_temp.m4s -vcodec copy -acodec copy video{bv_id}.mp4')
        # 删除临时文件




async def get_favorite_info(fav_id):
    try:
        # 获取收藏夹信息
        fav = favorite_list.FavoriteList(media_id=fav_id)
        
        # 检查是否为视频收藏夹
        if not fav.is_video_favorite_list():
            print(f"ERROR:错误：当前收藏夹（ID: {fav_id}）不是视频收藏夹")
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
                            print(f"ERROR:视频 {title} 已失效")
                            del_count += 1
                            #print(f"已失效视频：{del_count}")
                            #continue
                        # 保存到数据库
                        #查看数据库是否已经存在
                        cursor.execute('SELECT * FROM favorites where bv_id = ?', (bv_id,))
                        results = cursor.fetchall()
                        if results:
                            
                            print(results)
                            print(f"ERROR: {bv_id}视频已存在")
                            continue
                        else:
                            cursor.execute('''
                            INSERT INTO favorites (bv_id, av_id, url, title, uploader, play_count, favorite_time, upload_time, fav_title, collection_count, danmaku, is_deleted)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (bv_id, av_id, url, title, uploader, play_count, fav_time, upload_time, fav_title, collection_count, danmaku, is_deleted))
                        
                        total_videos += 1
                        print(f"已处理视频信息：{title}")
                        print(f"下载视频：{bv_id}")
                        
                        print(f"下载完成：{bv_id}")
                        br
                    except Exception as e:
                        print(f"ERROR:处理{bv_id}视频时出错：{str(e)}")
                        continue
                        
                page += 1
                
            except Exception as e:
                print(f"ERROR:获取第 {page} 页数据时出错：{str(e)}")
                break
                
        # 提交并关闭数据库连接
        conn.commit()
        conn.close()
        print(f"\n任务完成！共处理 {total_videos} 个视频")
        print(f"ERROR: {del_count} 个视频已失效")
        
    except Exception as e:
        print(f"ERROR:发生错误：{str(e)}")
        if 'conn' in locals():
            conn.close()

# 运行主函数
async def main():
    # 这里替换为你的收藏夹ID
    bv_id = "BV1Q4y7YWEhg"
    title = "测试"
    await download_video(bv_id,title)
    #fav_id = "183513431"
    #await get_favorite_info(fav_id)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
    
