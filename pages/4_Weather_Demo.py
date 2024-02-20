import streamlit as st
import requests
from datetime import datetime, date
import pytz
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import altair as alt

st.set_page_config(page_title="Weather Demo", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stSidebar"][aria-expanded="true"] > div:first-child{
        width: 400px;
    }
    [data-testid="stSidebar"][aria-expanded="false"] > div:first-child{
        width: 400px;
        margin-left: -400px;
    }
     
    """,
    unsafe_allow_html=True,
)

wmo_weather_codes = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog and depositing rime fog",
    48: "Fog and depositing rime fog",
    51: "Drizzle: Light intensity",
    53: "Drizzle: Moderate intensity",
    55: "Drizzle: Dense intensity",
    56: "Freezing Drizzle: Light intensity",
    57: "Freezing Drizzle: Dense intensity",
    61: "Rain: Slight intensity",
    63: "Rain: Moderate intensity",
    65: "Rain: Heavy intensity",
    66: "Freezing Rain: Light intensity",
    67: "Freezing Rain: Heavy intensity",
    71: "Snow fall: Slight intensity",
    73: "Snow fall: Moderate intensity",
    75: "Snow fall: Heavy intensity",
    77: "Snow grains",
    80: "Rain showers: Slight intensity",
    81: "Rain showers: Moderate intensity",
    82: "Rain showers: Violent intensity",
    85: "Snow showers slight intensity",
    86: "Snow showers heavy intensity",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

def add_weather_desc_column(df, weather_code_column):
    df['weather_desc'] = df[weather_code_column].map(wmo_weather_codes)
    return df


# Function to convert kelvin to fahrenheit
def kelvin_to_fahrenheit(kelvin):
    return round((kelvin - 273.15) * 9/5 + 32,1)

def days_between(d1, d2):
    return abs((d2 - d1).days)

def timeConvert(sun_time):
    # Parse the sun_time string into a datetime object
    converted_sun_time = datetime.strptime(sun_time, '%H:%M:%S')
    
    # Format the datetime object into a 12-hour format string with AM/PM and without seconds
    formatted_sun_time = converted_sun_time.strftime('%I:%M %p')
    
    return formatted_sun_time

def get_img_url(weather_data):
    icon_id = weather_data['weather'][0]['icon']
    icon_url = f"http://openweathermap.org/img/wn/{icon_id}@2x.png"
    return icon_url

# Function to perform direct geocoding using OpenWeatherMap's Geocoding API
def geocode_location(city_name, state_code, country_code, api_key, limit=1):
    base_url = "http://api.openweathermap.org/geo/1.0/direct"
    query = f"{city_name},{state_code},{country_code}"
    params = {
        'q': query,
        'limit': limit,
        'appid': api_key
    }
    response = requests.get(base_url, params=params)
    return response.json()

# Function to fetch current weather data using latitude and longitude
def fetch_weather_data(lat, lon, api_key):
    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        'lat': lat,
        'lon': lon,
        'appid': api_key
    }
    response = requests.get(base_url, params=params)
    return response.json()

def fetch_history_data(city_name, state_code, start_date, end_date, api_key, country_code='US'):
    # Geocode the location to get latitude and longitude
    geocoded_data = geocode_location(city_name, state_code, country_code, api_key)
    if not geocoded_data:
        return "Location not found. Please try again with a different city name."

    lat, lon = geocoded_data[0]['lat'], geocoded_data[0]['lon']

    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    base_url = "https://archive-api.open-meteo.com/v1/archive"

    # Setup the Open-Meteo API parameters
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.strftime('%Y-%m-%d'),  # Format the date as YYYY-MM-DD
        "end_date": end_date.strftime('%Y-%m-%d'),  # Format the date as YYYY-MM-DD
        "hourly": ["temperature_2m", "relative_humidity_2m", "rain", "snowfall", "snow_depth", "weather_code", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "is_day"],
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "sunrise", "sunset", "precipitation_sum", "rain_sum", "snowfall_sum", "precipitation_hours", "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant"],
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/New_York"
    }

    responses = openmeteo.weather_api(base_url, params=params)

    # Process the response
    response = responses[0]  # Assuming single location response for simplicity

    # Process hourly data. The order of variables needs to be the same as requested.
    hourly = response.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
    hourly_relative_humidity_2m = hourly.Variables(1).ValuesAsNumpy()
    hourly_rain = hourly.Variables(2).ValuesAsNumpy()
    hourly_snowfall = hourly.Variables(3).ValuesAsNumpy()
    hourly_snow_depth = hourly.Variables(4).ValuesAsNumpy()
    hourly_weather_code = hourly.Variables(5).ValuesAsNumpy()
    hourly_wind_speed_10m = hourly.Variables(6).ValuesAsNumpy()
    hourly_wind_direction_10m = hourly.Variables(7).ValuesAsNumpy()
    hourly_wind_gusts_10m = hourly.Variables(8).ValuesAsNumpy()
    hourly_is_day = hourly.Variables(9).ValuesAsNumpy()

    hourly_data = {"date": pd.date_range(
        start = pd.to_datetime(hourly.Time(), unit = "s"),
        end = pd.to_datetime(hourly.TimeEnd(), unit = "s"),
        freq = pd.Timedelta(seconds = hourly.Interval()),
        inclusive = "left"
    )}

    hourly_data["temperature_2m"] = hourly_temperature_2m
    hourly_data["relative_humidity_2m"] = hourly_relative_humidity_2m
    hourly_data["rain"] = hourly_rain
    hourly_data["snowfall"] = hourly_snowfall
    hourly_data["snow_depth"] = hourly_snow_depth
    hourly_data["weather_code"] = hourly_weather_code
    hourly_data["wind_speed_10m"] = hourly_wind_speed_10m
    hourly_data["wind_direction_10m"] = hourly_wind_direction_10m
    hourly_data["wind_gusts_10m"] = hourly_wind_gusts_10m
    hourly_data["is_day"] = hourly_is_day

    hourly_dataframe = pd.DataFrame(data = hourly_data)

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_weather_code = daily.Variables(0).ValuesAsNumpy()
    daily_temperature_2m_max = daily.Variables(1).ValuesAsNumpy()
    daily_temperature_2m_min = daily.Variables(2).ValuesAsNumpy()
    daily_temperature_2m_mean = daily.Variables(3).ValuesAsNumpy()
    daily_sunrise = daily.Variables(4).ValuesAsNumpy()
    daily_sunset = daily.Variables(5).ValuesAsNumpy()
    daily_precipitation_sum = daily.Variables(6).ValuesAsNumpy()
    daily_rain_sum = daily.Variables(7).ValuesAsNumpy()
    daily_snowfall_sum = daily.Variables(8).ValuesAsNumpy()
    daily_precipitation_hours = daily.Variables(9).ValuesAsNumpy()
    daily_wind_speed_10m_max = daily.Variables(10).ValuesAsNumpy()
    daily_wind_gusts_10m_max = daily.Variables(11).ValuesAsNumpy()
    daily_wind_direction_10m_dominant = daily.Variables(12).ValuesAsNumpy()

    daily_data = {"date": pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s"),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s"),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left"
    )}

    daily_data["weather_code"] = daily_weather_code
    daily_data["temperature_2m_max"] = daily_temperature_2m_max
    daily_data["temperature_2m_min"] = daily_temperature_2m_min
    daily_data["temperature_2m_mean"] = daily_temperature_2m_mean
    daily_data["sunrise"] = daily_sunrise
    daily_data["sunset"] = daily_sunset
    daily_data["precipitation_sum"] = daily_precipitation_sum
    daily_data["rain_sum"] = daily_rain_sum
    daily_data["snowfall_sum"] = daily_snowfall_sum
    daily_data["precipitation_hours"] = daily_precipitation_hours
    daily_data["wind_speed_10m_max"] = daily_wind_speed_10m_max
    daily_data["wind_gusts_10m_max"] = daily_wind_gusts_10m_max
    daily_data["wind_direction_10m_dominant"] = daily_wind_direction_10m_dominant

    daily_dataframe = pd.DataFrame(data = daily_data)

    return hourly_dataframe, daily_dataframe

def date_converter(human_date, date_format="%Y-%m-%d %H:%M:%S", timezone='US/Eastern'):
    """
    Convert a human-readable date in EST to Unix timestamp.
    
    Parameters:
    - human_date: str. The human-readable date string.
    - date_format: str. The format of the human-readable date.
    - timezone: str. The timezone of the human-readable date.
    
    Returns:
    - Unix timestamp: int. The Unix timestamp corresponding to the given human-readable date.
    """
    if human_date is None:
        human_date = datetime.now().strftime(date_format)
    # Create a timezone-aware datetime object
    est = pytz.timezone(timezone)
    dt_obj = datetime.strptime(human_date, date_format)
    dt_obj_est = est.localize(dt_obj)
    
    # Convert to Unix timestamp
    unix_timestamp = int(dt_obj_est.timestamp())
    
    return unix_timestamp

def unix_date_converter(unix_timestamp, timezone='US/Eastern', date_format="%H:%M:%S"):
    """
    Convert a Unix timestamp to a human-readable date in EST.
    
    Parameters:
    - unix_timestamp: int. The Unix timestamp to be converted.
    - timezone: str. The timezone for the converted date.
    - date_format: str. The format of the output human-readable date.
    
    Returns:
    - str. The human-readable date corresponding to the given Unix timestamp.
    """
    # Create a timezone-aware datetime object from the Unix timestamp
    utc_dt = datetime.utcfromtimestamp(unix_timestamp).replace(tzinfo=pytz.utc)
    
    # Convert UTC datetime to the specified timezone (EST by default)
    tz = pytz.timezone(timezone)
    dt_tz = utc_dt.astimezone(tz)
    
    # Format the timezone-aware datetime object as a string
    human_date = dt_tz.strftime(date_format)
    
    return human_date

# Streamlit UI for Weather Dashboard
st.title(':sun_behind_rain_cloud: Weather Dashboard :lightning_cloud:')
st.write(':point_right: Only enter cities and states within the United States.')

# Assuming the country code is US
country_code = "US"

# Your OpenWeatherMap API key
API_KEY = "f2745e66a83bde8eaaa86a6b9c2cd140"
DATE_FORMAT="""%Y-%m-%d %H:%M:%S"""

with st.container(border=True):
    city_name_col, state_code_col = st.columns([3, 1])
    with city_name_col:
        city_name = st.text_input("Enter City Here", placeholder="Type here...").lower().strip()
    with state_code_col:
        state_code = st.text_input("Enter State Here", placeholder="Type here...").lower().strip()
    submit = st.button('Submit')

with st.expander("Optional: Fetch Historic Weather", expanded=False):
    with st.container(border=True):
        start_date_col, end_date_col = st.columns(2)
        with start_date_col:
            start_date = st.date_input("Enter a Start Date", value=date.today())
            start_date_str = datetime.strftime(start_date, DATE_FORMAT)  # Convert to string
            unix_start_date = date_converter(start_date_str)  # Convert to Unix timestamp
            st.write('Your start date is: ', start_date)
            st.write('Your start date in Unix Date is: ', unix_start_date)
            st.write('Your converted unix timestamp is: ', unix_date_converter(unix_start_date))

        with end_date_col:
            end_date = st.date_input("Enter an End Date", value=date.today())
            end_date_str = datetime.strftime(end_date, DATE_FORMAT)  # Convert to string
            unix_end_date = date_converter(end_date_str)  # Convert to Unix timestamp
            st.write('Your end date is: ', end_date)
            st.write('Your end date in Unix Date is: ', unix_end_date)
            st.write('Your converted unix timestamp is: ', unix_date_converter(unix_end_date))
            submit_historical = st.button('Fetch Historical Weather')

sc1, sc2, sc3, sc4 = st.columns(4)


if submit:
    # Show and update progress bar
    bar = st.progress(0)
    if city_name and state_code:
        # Perform geocoding to get latitude and longitude
        geocoded_data = geocode_location(city_name, state_code, country_code, API_KEY)
        if geocoded_data:
            lat, lon = geocoded_data[0]['lat'], geocoded_data[0]['lon']
            # Fetch current weather data using the geocoded coordinates
            bar.progress(33)
            weather_data = fetch_weather_data(lat, lon, API_KEY)
            bar.progress(66)
            # Get the icon URL and display the weather icon
            icon_url = get_img_url(weather_data)
            st.write(f"It is currently {weather_data['weather'][0]['main'].lower()}:")
            st.image(icon_url, caption=f"{weather_data['weather'][0]['description']}")
            with sc1:
                with st.container(border=True):
                    st.metric(label="Current Temp", value=f"{kelvin_to_fahrenheit(weather_data['main']['temp'])} °F", delta=None, delta_color="normal", help=None, label_visibility="visible")
            with sc2:
                with st.container(border=True):
                    st.metric(label="Current Humidity", value=f"{weather_data['main']['humidity']} %", delta=None, delta_color="normal", help=None, label_visibility="visible")
            with sc3:
                with st.container(border=True):
                    st.metric(label="Sunrise", value=timeConvert(unix_date_converter(weather_data['sys']['sunrise'])), delta=None, delta_color="normal", help=None, label_visibility="visible")
            with sc4:
                with st.container(border=True):
                    st.metric(label="Sunset", value=timeConvert(unix_date_converter(weather_data['sys']['sunset'])), delta=None, delta_color="normal", help=None, label_visibility="visible")
            # Displaying the weather data - this can be formatted for better presentation
            st.json(weather_data)
            bar.progress(100)
        else:
            st.error("Location not found. Please try again with a different city name.")


# Streamlit UI for triggering the history data fetch
if submit_historical:
    bar = st.progress(0)
    hourly_data, daily_data = fetch_history_data(city_name, state_code, start_date, end_date, API_KEY)
    bar.progress(50)

    daily_data = add_weather_desc_column(daily_data, 'weather_code')

    if isinstance(hourly_data, str):
        st.error(hourly_data)  # Display error message if location not found
    else:
        if days_between(start_date, end_date) <= 365:
            # Displaying the hourly historical weather data as a line chart
            st.subheader("Hourly Historical Weather Data")
            st.line_chart(hourly_data.set_index('date')[['temperature_2m', 'relative_humidity_2m']])
            bar.progress(100)
        else:
            # Displaying the daily historical weather data as a line chart
            st.subheader("Daily Historical Weather Data")
            st.line_chart(daily_data.set_index('date')[['temperature_2m_mean', 'precipitation_sum']])

            weather_counts = daily_data['weather_desc'].value_counts().sort_values(ascending=False)

            weather_counts = pd.DataFrame(weather_counts).reset_index()
            weather_counts.columns = ['weather_desc', 'count']
            
            with st.container(border=True):
                chart = alt.Chart(weather_counts).mark_bar().encode(
                    x=alt.X('weather_desc', sort='-y'),
                    y=alt.Y('count'),
                    tooltip=['weather_desc', 'count']
                ).properties(
                    width=600,
                    height=400
                )

            # Display the chart in Streamlit
            st.subheader("Frequency of Daily Weather Events")
            st.altair_chart(chart, use_container_width=True)

            st.subheader("Tablized Daily Historical Data")
            st.write(daily_data)  # Displaying the daily historical weather data
            st.subheader("Tablized Hourly Historical Data")
            st.write(hourly_data)  # Displaying the hourly historical weather data
            bar.progress(100)

# TODO: Add windiest day of the date range selected
# date + speed / maybe wind direction

# TODO: Wind vector map for the date range selected or wind direction visual if radials present in data

# TODO: Revise Daily Date Range Selection for more charts
            
# TODO: Optimize Current Forecast to display nicely
            
# TODO: Fun idea. Add a race graph for the categories of weather over time
            
# TODO: Build functionality in API call to grab delta for current forecast
            
# TODO: Hide API Key into separate config file
            
# TODO: Add city comparison for A/B Testing!

# TODO: Add descriptive summany stats in score cards such as mean temperature across date range,
#       median temperature across date range, standard deviation (1-3x), mode, etc.