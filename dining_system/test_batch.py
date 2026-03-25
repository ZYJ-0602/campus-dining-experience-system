import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:5001/api/admin/dishes/batch_import', 
    data=json.dumps([{'window_id': 1, 'name': 'Test Dish', 'price': 9.99}]).encode(), 
    headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
print(res.read().decode())