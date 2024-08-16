import requests

url='https://www.tacobell.com/food/new?store=028915'

r= requests.get(url)

print(r.text)