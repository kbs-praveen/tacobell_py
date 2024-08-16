import scrapy
from scrapy_selenium import SeleniumRequest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TacoBellSpider(scrapy.Spider):
    name = 'tacobell_spider'
    allowed_domains = ['tacobell.com']
    start_urls = ['https://www.tacobell.com/food']

    def __init__(self, *args, **kwargs):
        super(TacoBellSpider, self).__init__(*args, **kwargs)
        self.processed_product_urls = set()

    def start_requests(self):
        yield SeleniumRequest(
            url=self.start_urls[0],
            callback=self.parse,
            wait_time=15,
            wait_until=EC.presence_of_all_elements_located(
                (By.XPATH, '//article[contains(@class, "styles_card__1se34")]')),
        )

    def parse(self, response):
        self.logger.info('Parsing the main page')
        items = response.xpath('//article[contains(@class, "styles_card__1se34")]')
        self.logger.info(f'Found {len(items)} items on the page.')

        for item in items:
            dynamic_value = item.xpath('.//a/@href').get().split('/')[-1]
            self.logger.info(f'Processing item with dynamic_value: {dynamic_value}')

            if dynamic_value:
                detail_url = f'https://www.tacobell.com/food/{dynamic_value}'
                self.logger.info(f'Requesting detail URL: {detail_url}')

                yield SeleniumRequest(
                    url=detail_url,
                    callback=self.parse_item,
                    meta={'name': dynamic_value},
                    wait_time=15,
                    wait_until=EC.presence_of_all_elements_located(
                        (By.XPATH, '//article[contains(@class, "styles_container__yxQpy styles_product-list__3QLx5")]')),
                )

    def parse_item(self, response):
        self.logger.info('Parsing item page')
        items = response.xpath('//div[contains(@class, "styles_card__1DpUa styles_product-card__1-cAT")]')

        self.logger.info(f'Found {len(items)} products on the page.')

        products = []
        for item in items:
            product_name = item.xpath('.//a[contains(@class, "styles_product-title__6KCyw")]/h4/text()').get()
            product_price = item.xpath('.//p[contains(@class, "styles_product-details__2VdYf")]/span[1]/text()').get()
            product_description = item.xpath(
                './/p[contains(@class, "styles_product-details__2VdYf")]/span[2]/text()').get()
            product_image_url = item.xpath(
                './/img[contains(@class, "styles_image__3bMG2 styles_product-image__p-OZn")]/@src').get()

            if product_name:
                product_name_encoded = product_name.replace(' ', '-').lower()
                item_name_encoded = response.meta['name']
                detail_url_product = f'https://www.tacobell.com/food/{item_name_encoded}/{product_name_encoded}'
                cleaned_url_product = detail_url_product.replace("®", "").replace("™", "").replace('~', '')

                if cleaned_url_product not in self.processed_product_urls:
                    self.processed_product_urls.add(cleaned_url_product)
                    self.logger.info(f'Processing URL: {cleaned_url_product}')

                    products.append({
                        'name': product_name,
                        'price': product_price,
                        'description': product_description,
                        'image_url': product_image_url,
                        'details': []  # Initialize an empty list to be filled in parse_details
                    })

        # Pass the accumulated products to the next callback
        yield SeleniumRequest(
            url=cleaned_url_product,
            callback=self.parse_details,
            meta={
                'name': response.meta['name'],
                'products': products  # Passing the entire list of products
            },
            wait_time=15,
            wait_until=EC.presence_of_all_elements_located(
                (By.XPATH, '//article[contains(@class, "styles_main-content__Av8Ro")]')),
        )

    def parse_details(self, response):
        products = response.meta.get('products', [])

        # Define the XPaths for different item structures
        items = response.xpath('//div[contains(@class, "styles_interactive__3pQZP styles_flex-card__-Gb6u")]')

        if not items:
            self.logger.info("No items found with the provided XPath")

        for product in products:
            details = []
            for item in items:
                name = item.xpath(
                    './/span[contains(@class, "styles_name__3-08P styles_text-shadow__OtfIt")]/text()').get()
                price = item.xpath('.//span[contains(@class, "styles_price-and-calories__13gpI")]/span[1]/text()').getall()
                # Join the extracted text content and clean it up
                price = ''.join(price).replace('+', '').strip()

                image_url = item.xpath('.//img[contains(@class, "styles_image__3bMG2")]/@src').get()

                # Debugging information
                self.logger.info(f"Extracted name: {name}")
                self.logger.info(f"Extracted price: {price}")
                self.logger.info(f"Extracted image_url: {image_url}")

                details.append({
                    'name': name.strip() if name else None,
                    'price': price.strip() if price else None,
                    'image_url': image_url.strip() if image_url else None,
                })

            product['details'] = details

        yield {
            'name': response.meta.get('name', 'N/A'),
            'products': products
        }