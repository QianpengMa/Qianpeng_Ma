import os
import re
from urllib.parse import urlparse, parse_qs

import requests
from lxml import etree


class MusicSpider:
    def __init__(self, output_dir="muc"):
        # 设置音乐保存文件夹
        # Set the folder used to save downloaded music files
        self.output_dir = output_dir

        # 如果文件夹不存在，则自动创建
        # Create the output folder automatically if it does not exist
        os.makedirs(self.output_dir, exist_ok=True)

        # 模拟浏览器请求头
        # Use a browser-like User-Agent for HTTP requests
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            )
        }

    def clean_url(self, url):
        # 删除网易云链接中的 /#，转换成普通网页地址
        # Remove "/#" from NetEase Music URLs so they can be requested normally
        return url.strip().replace("/#", "/")

    def get_song_id(self, url):
        # 从单曲链接中提取歌曲 ID
        # Extract the song ID from a single-track URL
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        if "id" in query and query["id"]:
            return query["id"][0]

        # 兼容某些非标准链接格式
        # Support some non-standard URL formats
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)

        return None

    def sanitize_filename(self, filename):
        # 删除 Windows 文件名中不能使用的字符
        # Remove characters that are invalid in Windows filenames
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)

        # 删除文件名前后的空格和句点
        # Remove leading and trailing spaces or periods
        filename = filename.strip(" .")

        return filename or "unknown_song"

    def get_song_name(self, song_id):
        # 请求歌曲页面以获取歌曲名称
        # Request the song page to obtain the track name
        song_page_url = f"https://music.163.com/song?id={song_id}"

        try:
            response = requests.get(
                song_page_url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException:
            return f"song_{song_id}"

        html = etree.HTML(response.text)

        # 尝试从网页标题中获取歌曲名称
        # Try to extract the track name from the page title
        title = html.xpath("//title/text()") if html is not None else []

        if title:
            name = title[0].strip()

            # 删除网易云网页标题中的网站名称
            # Remove the website name from the HTML page title
            name = re.sub(r"\s*-\s*网易云音乐\s*$", "", name)

            if name:
                return self.sanitize_filename(name)

        return f"song_{song_id}"

    def get_playlist_songs(self, url):
        # 请求歌单或专辑页面
        # Request a playlist or album page
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"请求页面失败 / Failed to request page: {error}")
            return []

        html = etree.HTML(response.text)

        if html is None:
            return []

        # 从页面隐藏歌曲列表中获取歌曲链接和名称
        # Extract song links and names from the hidden track list
        song_urls = html.xpath('//ul[contains(@class, "f-hide")]/li/a/@href')
        song_names = html.xpath('//ul[contains(@class, "f-hide")]/li/a/text()')

        songs = []

        for index, song_url in enumerate(song_urls):
            match = re.search(r"id=(\d+)", song_url)

            if not match:
                continue

            song_id = match.group(1)

            if index < len(song_names):
                song_name = self.sanitize_filename(song_names[index])
            else:
                song_name = f"song_{song_id}"

            songs.append((song_id, song_name))

        return songs

    def download_song(self, song_id, song_name=None):
        # 使用歌曲 ID 访问公开可访问的音频地址
        # Use the song ID to request the publicly accessible audio endpoint
        music_url = (
            "https://music.163.com/song/media/outer/url"
            f"?id={song_id}.mp3"
        )

        try:
            response = requests.get(
                music_url,
                headers=self.headers,
                timeout=20,
                allow_redirects=True
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"下载失败 / Download failed: {error}")
            return False

        # 检查服务器是否真正返回音频，而不是错误网页
        # Check whether the server returned audio instead of an HTML error page
        content_type = response.headers.get("Content-Type", "").lower()

        if "text/html" in content_type or "application/json" in content_type:
            print(
                f"歌曲 {song_id} 没有返回可下载音频。"
                " / No downloadable audio was returned."
            )
            return False

        # 如果没有提供歌曲名称，则自动获取
        # Fetch the track name automatically when no name is provided
        if not song_name:
            song_name = self.get_song_name(song_id)

        song_name = self.sanitize_filename(song_name)
        file_path = os.path.join(self.output_dir, f"{song_name}.mp3")

        # 将音频数据保存到本地文件
        # Save the downloaded audio data to a local file
        try:
            with open(file_path, "wb") as file:
                file.write(response.content)
        except OSError as error:
            print(f"保存文件失败 / Failed to save file: {error}")
            return False

        # 检查文件是否为空
        # Check whether the downloaded file is empty
        if os.path.getsize(file_path) == 0:
            os.remove(file_path)
            print("下载文件为空 / Downloaded file is empty.")
            return False

        print(f"下载完成 / Downloaded: {file_path}")
        return True

    def run(self, url):
        # 清理用户输入的网址
        # Clean the URL entered by the user
        url = self.clean_url(url)

        # 首先判断是否为单曲链接
        # First check whether the URL is a single-track link
        song_id = self.get_song_id(url)

        if "/song" in url and song_id:
            self.download_song(song_id)
            return

        # 如果不是单曲链接，则尝试解析歌单或专辑中的歌曲
        # Otherwise, try to parse tracks from a playlist or album page
        songs = self.get_playlist_songs(url)

        if not songs:
            print(
                "没有找到歌曲。请检查链接，或网页结构可能已经发生变化。"
                " / No tracks were found. Check the URL or the page structure."
            )
            return

        print(f"找到 {len(songs)} 首歌曲 / Found {len(songs)} tracks.")

        for song_id, song_name in songs:
            self.download_song(song_id, song_name)


if __name__ == "__main__":
    # 创建音乐爬虫对象
    # Create the music spider object
    spider = MusicSpider()

    # 输入网易云单曲、歌单或专辑链接
    # Enter a NetEase Music song, playlist, or album URL
    music_url = input("请输入网易云音乐链接 / Enter NetEase Music URL: ")

    # 开始解析并下载公开可访问的音乐资源
    # Start parsing and downloading publicly accessible music resources
    spider.run(music_url)
