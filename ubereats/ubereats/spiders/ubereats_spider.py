import scrapy
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class UberEatsSpider(scrapy.Spider):
    name = 'ubereat_spider'
    start_urls = [
        'https://www.ubereats.com/store/flintridge-pizza-kitchen/RxyR9w3aU-KVTHK2s9XGlg?ps=1'
    ]

    def __init__(self, *args, **kwargs):
        super(UberEatsSpider, self).__init__(*args, **kwargs)
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Uncomment to run in headless mode
        chrome_options.add_argument("--disable-gpu")
        self.driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)

    def parse(self, response):
        self.driver.get(response.url)

        # Extract the JSON data from the <script type="application/ld+json"> tag
        json_data = response.xpath('//script[@type="application/ld+json"]/text()').get()
        if json_data:
            try:
                data = json.loads(json_data)
                menu_data = self.parse_menu(data.get('hasMenu', {}))  # Parse initial menu structure

                # Now handle dynamic content for menu items
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'li[data-test^="store-item-"]'))
                    )

                    items = self.driver.find_elements(By.CSS_SELECTOR, 'li[data-test^="store-item-"]')

                    # Extract and append item details to the menu
                    for item in items:
                        try:
                            item.click()
                            self.handle_popup()
                            details = self.extract_item_details()
                            if details:
                                menu_data = self.append_item_details_to_menu(menu_data, details)  # Append details
                            self.driver.back()
                            WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, 'li[data-test^="store-item-"]'))
                            )
                        except Exception as e:
                            self.logger.error(f"Error occurred while processing item: {e}")
                            continue

                    # Yield the final restaurant data with complete menu details
                    restaurant = {
                        'data': {
                            'Context': data.get('@context'),
                            'Id': data.get('@id'),
                            'Title': data.get('name'),
                            'serves_cuisine': data.get('servesCuisine'),
                            'restaurantAddress': {
                                'Type': data.get('address', {}).get('@type'),
                                'street': data.get('address', {}).get('streetAddress'),
                                'city': data.get('address', {}).get('addressLocality'),
                                'state': data.get('address', {}).get('addressRegion'),
                                'postal_code': data.get('address', {}).get('postalCode'),
                                'country': data.get('address', {}).get('addressCountry'),
                            },
                            'geo': {
                                'type': data.get('geo', {}).get('@type'),
                                'latitude': data.get('geo', {}).get('latitude'),
                                'longitude': data.get('geo', {}).get('longitude')
                            },
                            'telephone': data.get('telephone'),
                            'price_range': data.get('priceRange'),
                            'rating': data.get('aggregateRating', {}).get('ratingValue'),
                            'review_count': data.get('aggregateRating', {}).get('reviewCount'),
                            'cuisine': data.get('servesCuisine', []),
                            'images': data.get('image', []),
                            'opening_hours': self.parse_opening_hours(data.get('openingHoursSpecification', [])),
                            'categories': menu_data  # Final menu with appended details
                        }
                    }
                    yield restaurant

                except Exception as e:
                    self.logger.error(f"Error occurred while extracting dynamic content: {e}")

            except json.JSONDecodeError as e:
                self.logger.error(f'Error decoding JSON: {e}')

    def parse_opening_hours(self, hours_data):
        opening_hours = []
        for hours in hours_data:
            days = hours.get('dayOfWeek', [])
            if not isinstance(days, list):
                days = [days]
            for day in days:
                opening_hours.append({
                    'day': day,
                    'opens': hours.get('opens'),
                    'closes': hours.get('closes')
                })
        return opening_hours

    def parse_menu(self, menu_data):
        menu = []
        for section in menu_data.get('hasMenuSection', []):
            section_name = section.get('name')
            items = section.get('hasMenuItem', [])
            menu_items = []

            for item in items:
                offers = []
                offer_data = item.get('offers', {})
                if offer_data:
                    offer = {
                        'type': offer_data.get('@type'),
                        'price': offer_data.get('price'),
                        'price_currency': offer_data.get('priceCurrency')
                    }
                    offers.append(offer)

                menu_item = {
                    'type': item.get('@type'),
                    'name': item.get('name'),
                    'description': item.get('description'),
                    'image_url': None,  # Placeholder for the image URL to be added later
                    'offers': offers,
                    'ingredientsGroups': None  # Placeholder for details to be added later
                }
                menu_items.append(menu_item)

            section_data = {
                'title': section_name,
                'menu': menu_items
            }
            menu.append(section_data)

        return menu

    def handle_popup(self):
        try:
            WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[role="dialog"]'))
            )
            close_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-testid="close-button"]')
            close_button.click()
            WebDriverWait(self.driver, 5).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, 'div[role="dialog"]'))
            )
        except Exception as e:
            self.logger.info(f"Popup not found or already closed: {e}")

    def extract_item_details(self):
        details = []
        item_name = None
        image_url = None

        try:
            item_name_element = self.driver.find_element(By.CSS_SELECTOR, 'h1.ft.fv.fu.fs.al.cg')
            item_name = item_name_element.text.strip() if item_name_element else None
        except Exception as e:
            self.logger.error(f"Error extracting item name: {e}")

        try:
            image_element = self.driver.find_element(By.CSS_SELECTOR, 'div.cj.ae.bl.kx img')
            image_url = image_element.get_attribute('src') if image_element else None
        except Exception as e:
            self.logger.error(f"Error extracting image URL: {e}")

        try:
            detail_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="customization-pick-many"]')

            for element in detail_elements:
                category_name = element.find_element(By.CSS_SELECTOR, 'div.al.aq.b9.f3').text
                options = element.find_elements(By.CSS_SELECTOR, 'label')
                option_details = []

                for option in options:
                    try:
                        name = option.find_element(By.CSS_SELECTOR, 'div.be.bf.bg.bh.g3.or').text
                    except Exception as e:
                        self.logger.error(f"Error extracting option name: {e}")
                        name = None

                    try:
                        price = option.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g3.bn').text
                    except Exception as e:
                        self.logger.error(f"Error extracting option price: {e}")
                        price = None

                    option_details.append(
                        {'name': name.strip() if name else None, 'price': price.strip() if price else None})

                details.append(
                    {'name': category_name.strip() if category_name else None, 'ingredients': option_details})

        except Exception as e:
            self.logger.error(f"Error extracting details: {e}")

        return {'item_name': item_name, 'image_url': image_url,
                'item_details': details} if details or item_name else None

    def append_item_details_to_menu(self, menu, item_details):
        if not item_details:
            return menu

        item_name = item_details.get('item_name')
        image_url = item_details.get('image_url')
        if not item_name:
            return menu

        for section in menu:
            for menu_item in section['menu']:
                if menu_item['name'] == item_name:
                    menu_item['ingredientsGroups'] = item_details['item_details']
                    if image_url:
                        menu_item['image_url'] = image_url  # Add the image URL before offers
                    return menu  # Exit after matching item is found

        return menu

    def closed(self, reason):
        self.driver.quit()
