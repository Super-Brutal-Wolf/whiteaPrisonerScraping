from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
import speech_recognition as sr
import pandas as pd
import soundfile
import urllib
import time
import random
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

required_env_vars = ["BASE_URL", "LOGIN_URL", "USERNAME", "PASSWORD"]
missing_env_vars = [var for var in required_env_vars if os.getenv(var) is None]
if missing_env_vars:
    raise EnvironmentError(f"Missing environment variables: {missing_env_vars}")

BASE_URL = os.getenv("BASE_URL")
LOGIN_URL = os.getenv("LOGIN_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

def setup_driver():
    chrome_options = Options()
    # Uncomment the line below if you want to run in headless mode
    # chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def login(driver):
    try:
        print("Attempting to log in...")
        driver.get(LOGIN_URL)
        
        # Wait for username field to be present
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "edit-name"))
        )
        username_field.send_keys(USERNAME)
        
        # Find and fill password field
        password_field = driver.find_element(By.ID, "edit-pass")
        password_field.send_keys(PASSWORD)
        
        # Wait for and switch to the reCAPTCHA iframe
        recaptcha_frame = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="user-login-form"]/fieldset/div/div/div/div/iframe'))
        )
        driver.switch_to.frame(recaptcha_frame)

        # Wait for checkbox to be clickable and scroll it into view
        captcha_trigger_check = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "recaptcha-checkbox-border"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", captcha_trigger_check)
        
        # Try multiple click methods
        try:
            captcha_trigger_check.click()
        except:
            try:
                driver.execute_script("arguments[0].click();", captcha_trigger_check)
            except:
                actions = webdriver.ActionChains(driver)
                actions.move_to_element(captcha_trigger_check).click().perform()
            
        driver.switch_to.default_content()

        try:
            # Wait for and switch to the audio challenge iframe
            audio_frame = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div[4]/iframe'))
            )
            driver.switch_to.frame(audio_frame)
            
            # Wait for audio button to be clickable
            audio_method_trigger = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="recaptcha-audio-button"]'))
            )
            audio_method_trigger.click()

            # Get audio source and download
            audio_src = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'audio-source'))
            ).get_attribute('src')
            
            file_path = os.path.join(os.getcwd(), "captcha1.wav")
            urllib.request.urlretrieve(audio_src, file_path)
            
            # Process audio with better error handling
            try:
                data, samplerate = soundfile.read('captcha1.wav')
                soundfile.write('processed_audio.wav', data, samplerate, subtype='PCM_16')
                recognizer = sr.Recognizer()

                with sr.AudioFile("processed_audio.wav") as source:
                    audio_data = recognizer.record(source)
                    convert_audio_text = recognizer.recognize_google(audio_data)
                    print(f"Recognized audio text: {convert_audio_text}")
            except Exception as e:
                print(f"Audio processing failed: {str(e)}")
                raise

            # Input the recognized text
            audio_text_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "audio-response"))
            )
            audio_text_input.send_keys(convert_audio_text)

            # Click verify button
            verify_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "recaptcha-verify-button"))
            )
            verify_button.click()
        except:
            pass
        driver.switch_to.default_content()
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "edit-submit"))
        )
        login_button.click()
        
        # Wait for login to complete
        WebDriverWait(driver, 10).until(
            EC.url_changes(LOGIN_URL)
        )
        
        print("Login successful!")
        return True
        
    except Exception as e:
        print(f"Login failed! Trying again...")
        return login(driver)

def save_data(all_data, file_name):
    try:
        # Path for the master file containing all historical data
        master_file = "prisoner_data/prisoner_data_all.xlsx"
        
        # Convert new data to DataFrame
        new_df = pd.DataFrame(all_data)
        
        if os.path.exists(master_file):
            # Read existing master data
            master_df = pd.read_excel(master_file)
            
            # Create unique identifiers for comparison
            new_df['unique_id'] = new_df['DOC/Inmate #'].astype(str) + '_' + new_df['First Name'] + '_' + new_df['Last Name']
            master_df['unique_id'] = master_df['DOC/Inmate #'].astype(str) + '_' + master_df['First Name'] + '_' + master_df['Last Name']
            
            # Find new listings by comparing unique identifiers
            existing_ids = set(master_df['unique_id'])
            new_df['is_new'] = ~new_df['unique_id'].isin(existing_ids)
            new_df_filtered = new_df[new_df['is_new']].drop(['unique_id', 'is_new'], axis=1)
            
            if not new_df_filtered.empty:
                # Save new listings to today's file
                new_df_filtered.to_excel(file_name, index=False)
                print(f"Saved {len(new_df_filtered)} new listings to {file_name}")
                
                # Update master file with new listings
                updated_master_df = pd.concat([master_df.drop('unique_id', axis=1), new_df_filtered], ignore_index=True)
                updated_master_df.to_excel(master_file, index=False)
                print(f"Updated master file with {len(new_df_filtered)} new listings")
            else:
                print("No new listings found")
        else:
            # If master file doesn't exist, create it with all current data
            new_df.to_excel(master_file, index=False)
            print(f"Created master file with {len(new_df)} listings")
            
            # Save all data to today's file as well
            new_df.to_excel(file_name, index=False)
            print(f"Saved {len(new_df)} listings to {file_name}")
            
    except Exception as e:
        print(f"Error in save_data: {str(e)}")
        raise

def main():
    folder_name = "prisoner_data"
    file_name = f"{folder_name}/prisoner_data_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    all_data = []
    is_last_page = False
    driver = setup_driver()
    try:
        if login(driver):
            driver.get(f"{BASE_URL}/?page=84")
            while True:
                # Wait for the container to be present
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".religion-prison-pen-pals-row.views-row"))
                )
                
                person_elements = driver.find_elements(By.CSS_SELECTOR, ".religion-prison-pen-pals-row.views-row")
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, "ul.pager li.next a")
                    next_button_href = next_button.get_attribute('href')
                except:
                    is_last_page = True

                person_list = {}
                for person in person_elements:
                    person_element = person.find_elements(By.TAG_NAME, "a")[1]
                    person_href = person_element.get_attribute('href')
                    person_name = person_element.text.strip()
                    person_list[person_name] = person_href

                for person_name, person_href in person_list.items():
                    inmate_number = None
                    address_line_1 = None
                    address_line_2 = None
                    city = None
                    state = None
                    zip_code = None

                    # Navigate to the person's page
                    driver.get(person_href)

                    # Wait for the table to be present
                    standard_point = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.tablewrapper.penpal-contact-table'))
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'start', behavior: 'smooth'});", standard_point)

                    # Wait for and get the inmate number
                    individual_info_table = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.tablewrapper.penpal-contact-table tbody tr:nth-child(3) td:first-child'))
                    )
                    inmate_number = individual_info_table.text.strip().split('\n')[0].split('#')[-1].strip()

                    # Wait for and get address details
                    individual_info_details = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.tablewrapper.penpal-contact-table .notranslate p'))
                    )
                    
                    name_parts = person_name.split(' ')
                    first_name = name_parts[0] if name_parts else ""
                    last_name = name_parts[-1] if len(name_parts) > 1 else ""
                    
                    address_line_1 = individual_info_details.find_element(By.CLASS_NAME, 'address-line1').text.strip()
                    try:
                        address_line_2 = individual_info_details.find_element(By.CLASS_NAME, 'address-line2').text.strip()
                    except:
                        address_line_2 = None
                    city = individual_info_details.find_element(By.CLASS_NAME, 'locality').text.strip()
                    state = individual_info_details.find_element(By.CLASS_NAME, 'administrative-area').text.strip()
                    zip_code = individual_info_details.find_element(By.CLASS_NAME, 'postal-code').text.strip()
                    
                    individual_prisoner_info = {
                        "First Name": first_name,
                        "Last Name": last_name,
                        "DOC/Inmate #": f"#{inmate_number}",
                        "Address Line 1": address_line_1,
                        "Address Line 2": address_line_2,
                        "City": city,
                        "State": state,
                        "ZipCode": zip_code,
                    }

                    print(f"Successfully processed prisoner info for {first_name} {last_name}")
                    
                    all_data.append(individual_prisoner_info)
                    time.sleep(random.uniform(1, 3))
                
                if not is_last_page:
                    print(f"Navigating to next page: {next_button_href}")
                    driver.get(next_button_href)
                    time.sleep(random.uniform(1, 3))
                else:
                    break
            
            # Save data after all scraping is complete
            save_data(all_data, file_name)
                        
    except Exception as e:
        print(f"Main process error: {str(e)}")
    finally:
        driver.quit()
        print("Scraping completed.")

if __name__ == "__main__":
    main()