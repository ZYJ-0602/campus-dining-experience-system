import urllib.request
req = urllib.request.Request('http://127.0.0.1:5001/api/admin/dishes')
res = urllib.request.urlopen(req)
print(res.read().decode())