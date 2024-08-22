import scrapy
from scrapy_selenium import SeleniumRequest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging

class TacoBellSpider(scrapy.Spider):
    name = 'tacobell_spider'
    allowed_domains = ['tacobell.com']
    start_urls = ['https://www.tacobell.com/food']

    def __init__(self, *args, **kwargs):
        super(TacoBellSpider, self).__init__(*args, **kwargs)
        self.processed_product_urls = set()
        self.products_by_dynamic_value = {}  # Dictionary to store products by dynamic value
        self.product_count = {}  # Keep track of the number of products processed per dynamic value

    def start_requests(self):
        yield SeleniumRequest(
            url=self.start_urls[0],
            callback=self.parse,
            wait_time=30,
        )

    def parse(self, response):
        driver = response.meta.get('driver')
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler'))
        ).click()
        logging.info('Cookie consent accepted.')
        self.logger.info('Parsing the main page')
        items = response.xpath('//article[contains(@class, "styles_card__1se34")]')
        self.logger.info(f'Found {len(items)} items on the page.')

        for item in items:
            dynamic_value = item.xpath('.//a/@href').get().split('/')[-1]
            self.logger.info(f'Processing item with dynamic_value: {dynamic_value}')
            item_name = item.xpath('.//span[contains(@class, "styles_label__3Sj9r")]/text()').get()

            if dynamic_value:
                detail_url = f'https://www.tacobell.com/food/{dynamic_value}'
                self.logger.info(f'Requesting detail URL: {detail_url}')

                # Initialize the list for the current dynamic value
                self.products_by_dynamic_value[dynamic_value] = []
                self.product_count[dynamic_value] = 0

                yield SeleniumRequest(
                    url=detail_url,
                    callback=self.parse_item,
                    meta={'name': dynamic_value, 'item_name': item_name},
                    wait_time=30,
                )

    def parse_item(self, response):
        self.logger.info('Parsing item page')
        items = response.xpath('//div[contains(@class, "styles_card__1DpUa styles_product-card__1-cAT")]')

        self.logger.info(f'Found {len(items)} products on the page.')

        dynamic_value = response.meta['name']

        for item in items:
            product_name = item.xpath('.//a[contains(@class, "styles_product-title__6KCyw")]/h4/text()').get()
            product_price = item.xpath('.//p[contains(@class, "styles_product-details__2VdYf")]/span[1]/text()').get()
            product_price = ''.join(product_price).replace('$', '').strip()
            product_description = item.xpath(
                './/p[contains(@class, "styles_product-details__2VdYf")]/span[2]/text()').get()
            product_image_url = item.xpath(
                './/img[contains(@class, "styles_image__3bMG2 styles_product-image__p-OZn")]/@src').get()
            product_param = item.xpath('.//a[contains(@class, "styles_product-title__6KCyw")]/@href').get().split('/')[
                -1]
            self.logger.info(f'Processing item with dynamic_value: {product_param}')

            if product_name:
                item_name_encoded = response.meta['name']
                detail_url_product = f'https://www.tacobell.com/food/{item_name_encoded}/{product_param}'
                cleaned_url_product = detail_url_product.replace("®", "").replace("™", "").replace('~', '')

                if cleaned_url_product not in self.processed_product_urls:
                    self.processed_product_urls.add(cleaned_url_product)
                    self.logger.info(f'Processing URL: {cleaned_url_product}')

                    product = {
                        'name': product_name,
                        'price': product_price,
                        'description': product_description,
                        'image_url': product_image_url,
                        'Ingredients details': []  # Initialize an empty list to be filled in parse_details
                    }

                    # Add the product to the list for the current dynamic value
                    self.products_by_dynamic_value[dynamic_value].append(product)

                    # Increment the product count
                    self.product_count[dynamic_value] += 1

                    # Pass the individual product to the next callback
                    yield SeleniumRequest(
                        url=cleaned_url_product,
                        callback=self.parse_details,
                        meta={
                            'name': response.meta['name'],
                            'item_name': response.meta['item_name'],
                            'product': product,  # Passing the individual product
                            'dynamic_value': dynamic_value,
                            'total_products': len(items)  # Total products in the current dynamic value
                        },
                        wait_time=30,
                    )

    def parse_details(self, response):
        product = response.meta.get('product', {})
        dynamic_value = response.meta.get('dynamic_value')

        items = response.xpath('//div[contains(@class, "styles_interactive__3pQZP styles_flex-card__-Gb6u")]')

        if not items:
            self.logger.info("No items found with the provided XPath")

        details = []
        for item in items:
            category_name = item.xpath(
                './/h3[contains(@class, "styles_customize-section-title__3Pb4I")]/text()').get()
            name = item.xpath(
                './/span[contains(@class, "styles_name__3-08P styles_text-shadow__OtfIt")]/text()').get()
            price = item.xpath('.//span[contains(@class, "styles_price-and-calories__13gpI")]/span[1]/text()').getall()
            # Join the extracted text content and clean it up
            price = ''.join(price).replace('+', '').replace('$', '').strip()

            image_url = item.xpath('.//img[contains(@class, "styles_image__3bMG2")]/@src').get()

            self.logger.info(f"Extracted name: {name}")
            self.logger.info(f"Extracted price: {price}")
            self.logger.info(f"Extracted image_url: {image_url}")

            details.append({
                'category_name': category_name.strip() if category_name else None,
                'name': name.strip() if name else None,
                'price': price.strip() if price else None,
                'image_url': image_url.strip() if image_url else None,
            })

        # Ensure the details belong to the correct product
        if 'Ingredients details' in product:
            product['Ingredients details'].extend(details)
        else:
            product['Ingredients details'] = details

        # After processing the details, check if this is the last product for the current dynamic value
        dynamic_value_products = self.products_by_dynamic_value.get(dynamic_value, [])
        last_product = dynamic_value_products[-1] if dynamic_value_products else None

        if product == last_product:
            # Yield the accumulated products as a list
            yield {
                'Title': response.meta.get('item_name', 'N/A'),
                'Menu': dynamic_value_products
            }