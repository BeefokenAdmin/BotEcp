import requests

url = 'http://192.168.0.3/ecp/php/api.php?action=get_expired_signatures'
response = requests.get(url)

print(f"Status Code: {response.status_code}")
print(f"Response Headers: {response.headers}")
print(f"Response Content: {response.content.decode('utf-8')}")