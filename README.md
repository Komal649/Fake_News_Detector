# Fake News Detector

A Flask-based web application that detects fake news using AI and multiple verification sources. Users can analyze text, URLs, and images to determine the credibility of news content.

## Features

- Analyze news articles by entering text
- Verify news from URLs
- Image-based fake news detection
- Analytics dashboard
- AI-powered analysis using Groq LLM
- Cross-check news using NewsAPI
- Google Custom Search integration for fact verification
- User-friendly web interface

##  Tech Stack

- Python
- Flask
- HTML
- CSS
- JavaScript
- Groq API
- NewsAPI
- Google Custom Search API

## Project Structure

```
Fake_News_Detector/
│── app.py
│── requirements.txt
│── .env
│── templates/
│   ├── dashboard.html
│   ├── text.html
│   ├── url.html
│   ├── image.html
│   └── analytics.html
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Komal649/Fake_News_Detector.git
cd Fake_News_Detector
```

### 2. Create a virtual environment

Windows

```bash
python -m venv venv
venv\Scripts\activate
```

Mac/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

Add the following environment variables:

```env
GROQ_API_KEY=your_groq_api_key
NEWS_API_KEY=your_news_api_key
GOOGLE_API_KEY=your_google_api_key
SEARCH_ENGINE_ID=your_search_engine_id
```

### 5. Run the application

```bash
python app.py
```

Open your browser and visit

```
http://127.0.0.1:5000/
```

## Screenshots

Add screenshots of:

- Dashboard
  <img width="880" height="679" alt="image" src="https://github.com/user-attachments/assets/d795798e-5de7-40fb-a40d-4999b834cc17" />

- Text Analysis
  <img width="828" height="619" alt="image" src="https://github.com/user-attachments/assets/fe0de86b-939e-466d-9685-d3e26422fef1" />

- URL Analysis
  <img width="751" height="406" alt="image" src="https://github.com/user-attachments/assets/b6fe85b2-c73c-4e32-8de3-8a2bf1e897e7" />

- Image Analysis
  <img width="906" height="558" alt="image" src="https://github.com/user-attachments/assets/2f9c94c1-0dac-4734-8e37-3c0114d46e98" />

- Analytics Dashboard
  <img width="860" height="713" alt="image" src="https://github.com/user-attachments/assets/94fe07bb-ad05-4697-93fb-dabe198bc4bb" />


## Environment Variables

This project requires the following APIs:

- Groq API
- NewsAPI
- Google Custom Search API

**Do not commit your `.env` file to GitHub.**

## Future Improvements

- User authentication
- History of analyzed news
- Support for multiple languages
- Improved image verification
- Deployment on Render/Heroku

## Author

**Komal B**
