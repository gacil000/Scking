import urllib.request, json, re
url = 'https://rapidapi.com/thetechguy32711/api/instagram-scraper-stable-api'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    paths = re.findall(r'\"route\":\"([^\"]+)\"', html)
    print('Found paths:', set(paths))
except Exception as e:
    print(e)
