import scrapy
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import re  # Import regular expressions module


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
        self.data = {}  # Initialize a list to store the data
        self.section_names = set()  # Initialize a set to store unique section names

    def parse(self, response):
        self.driver.get(response.url)

        # Extract the JSON data from the <script type="application/ld+json"> tag
        json_data = response.xpath('//script[@type="application/ld+json"]/text()').get()
        if json_data:
            try:
                data = json.loads(json_data)
                menu_data = self.parse_menu(data.get('hasMenu', {}))  # Parse initial menu structure

                # Track unique section names
                self.section_names.update(section['title'] for section in menu_data)

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
                            "menu_id": 18344,
                            'titleURL': data.get('@id'),
                            'title_id': '',
                            'Context': data.get('@context'),
                            'title': data.get('name'),
                            'images': data.get('image', []),
                            'LogoURL': '',

                            'restaurantAddress': {
                                '@type': data.get('address', {}).get('@type'),
                                'streetAddress': data.get('address', {}).get('streetAddress'),
                                'addressLocality': data.get('address', {}).get('addressLocality'),
                                'addressRegion': data.get('address', {}).get('addressRegion'),
                                'postalCode': data.get('address', {}).get('postalCode'),
                                'addressCountry': data.get('address', {}).get('addressCountry'),
                            },
                            'storeOpeningHours': self.parse_opening_hours(data.get('openingHoursSpecification', [])),
                            'priceRange': data.get('priceRange'),
                            'telephone': data.get('telephone'),
                            'ratingValue': data.get('aggregateRating', {}).get('ratingValue'),
                            'ratingCount': data.get('aggregateRating', {}).get('reviewCount'),
                            'latitude': data.get('geo', {}).get('latitude'),
                            'longitude': data.get('geo', {}).get('longitude'),
                            'cuisine': data.get('servesCuisine', []),
                            'menu_groups': list(self.section_names),  # Add unique section names to menu_groups

                            'categories': menu_data  # Final menu with appended details
                        }
                    }
                    yield restaurant
                    self.data = restaurant  # Store the data in the list

                except Exception as e:
                    self.logger.error(f"Error occurred while extracting dynamic content: {e}")

            except json.JSONDecodeError as e:
                self.logger.error(f'Error decoding JSON: {e}')

    def parse_opening_hours(self, hours_data):
        # Define the days of the week in the correct order
        days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

        # Create a dictionary to hold the opening hours for each day
        hours_dict = {day: None for day in days_of_week}

        def format_time(time_str):
            """Helper function to format the time string as HH:MM."""
            if not time_str:
                return "00:00"
            time_parts = time_str.split(':')
            if len(time_parts) == 1:
                return f"{time_parts[0]}:00"
            elif len(time_parts) == 2:
                return f"{time_parts[0].zfill(2)}:{time_parts[1].zfill(2)}"
            return time_str

        # Populate the dictionary with the opening hours from the input data
        for hours in hours_data:
            days = hours.get('dayOfWeek', [])
            if not isinstance(days, list):
                days = [days]
            opens = format_time(hours.get('opens', ''))
            closes = format_time(hours.get('closes', ''))
            for day in days:
                if day in hours_dict:
                    hours_dict[day] = f"{opens}-{closes}"

        # Convert the dictionary to a list of formatted strings
        store_opening_hours = [f"{day} {hours_dict[day]}" for day in days_of_week if hours_dict[day] is not None]

        return store_opening_hours

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

        # Extract "pick many" options
        try:
            detail_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="customization-pick-many"]')

            for element in detail_elements:
                category_name = element.find_element(By.CSS_SELECTOR, 'div.fs.hy.fu.hz.g4').text
                text = element.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g4').text

                # Use regular expression to find the number in the text
                match = re.search(r'(\d+)', text)

                # Extract the number if found, otherwise default to 0
                requires_selection_max = int(match.group(1)) if match else 0

                options = element.find_elements(By.CSS_SELECTOR, 'label')
                option_details = []

                for option in options:
                    try:
                        name = option.find_element(By.CSS_SELECTOR, 'div.be.bf.bg.bh.g3.os').text
                    except Exception as e:
                        self.logger.error(f"Error extracting option name: {e}")
                        name = None

                    try:
                        price_text = option.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g3.bn').text
                        price_cleaned = re.sub(r'[^\d.]+', '', price_text).strip()
                        left_half_price = float(
                            price_cleaned) if price_cleaned else 0.0  # Default to 0.0 if price is not found or is empty
                    except Exception as e:
                        self.logger.error(f"Error extracting option price: {e}")
                        left_half_price = 0.0  # Default to 0.0 if price is not found

                    try:
                        price_text = option.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g3.bn').text
                        price_cleaned = re.sub(r'[^\d.]+', '', price_text).strip()
                        right_half_price = float(
                            price_cleaned) if price_cleaned else 0.0  # Default to 0.0 if price is not found or is empty
                    except Exception as e:
                        self.logger.error(f"Error extracting option price: {e}")
                        right_half_price = 0.0  # Default to 0.0 if price is not found

                    try:
                        # Calculate price by summing left_half_price and right_half_price
                        price = left_half_price + right_half_price
                    except Exception as e:
                        self.logger.error(f"Error calculating total price: {e}")
                        price = 0.0  # Default to 0.0 if price calculation fails

                    option_details.append(
                        {'name': name.strip() if name else None, 'possibleToAdd': 1, 'price': price,
                         'leftHalfPrice': left_half_price, 'rightHalfPrice': right_half_price})

                details.append(
                    {'type': "general", 'name': category_name.strip() if category_name else None, 'requiresSelectionMin': 0, 'requiresSelectionMax': requires_selection_max if requires_selection_max else None, 'ingredients': option_details})

        except Exception as e:
            self.logger.error(f"Error extracting details (pick many): {e}")

        # Extract "pick one" options
        try:
            pick_one_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="customization-pick-one"]')

            for element in pick_one_elements:
                category_name = element.find_element(By.CSS_SELECTOR, 'div.fs.hy.fu.hz.g4').text
                text = element.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g4').text

                # Use regular expression to find the number in the text
                match = re.search(r'(\d+)', text)

                # Extract the number if found, otherwise default to 0
                requires_selection_max = int(match.group(1)) if match else 0

                options = element.find_elements(By.CSS_SELECTOR, 'label')
                option_details = []

                for option in options:
                    try:
                        name = option.find_element(By.CSS_SELECTOR, 'div.be.bf.bg.bh.g3.os').text
                    except Exception as e:
                        self.logger.error(f"Error extracting option name: {e}")
                        name = None

                    try:
                        price_text = option.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g3.bn').text
                        price_cleaned = re.sub(r'[^\d.]+', '', price_text).strip()
                        left_half_price = float(
                            price_cleaned) if price_cleaned else 0.0  # Default to 0.0 if price is not found or is empty
                    except Exception as e:
                        self.logger.error(f"Error extracting option price: {e}")
                        left_half_price = 0.0  # Default to 0.0 if price is not found

                    try:
                        price_text = option.find_element(By.CSS_SELECTOR, 'div.be.bf.g1.dj.g3.bn').text
                        price_cleaned = re.sub(r'[^\d.]+', '', price_text).strip()
                        right_half_price = float(
                            price_cleaned) if price_cleaned else 0.0  # Default to 0.0 if price is not found or is empty
                    except Exception as e:
                        self.logger.error(f"Error extracting option price: {e}")
                        right_half_price = 0.0  # Default to 0.0 if price is not found

                    try:
                        # Calculate price by summing left_half_price and right_half_price
                        price = left_half_price + right_half_price
                    except Exception as e:
                        self.logger.error(f"Error calculating total price: {e}")
                        price = 0.0  # Default to 0.0 if price calculation fails

                    option_details.append(
                        {'name': name.strip() if name else None, 'possibleToAdd': 1, 'price': price,
                         'leftHalfPrice': left_half_price, 'rightHalfPrice': right_half_price})

                details.append(
                    {'type': "general", 'name': category_name.strip() if category_name else None, 'requiresSelectionMin': 0, 'requiresSelectionMax': requires_selection_max.strip()  if requires_selection_max else None, 'ingredients': option_details})

        except Exception as e:
            self.logger.error(f"Error extracting details (pick one): {e}")

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
        # Save the data to a JSON file
        with open('ubereats_data.json', 'w') as f:
            json.dump(self.data, f, indent=4)