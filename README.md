# AI Stock Intelligence Web App

This project is a full-stack web platform for US stock analysis.

## Features

- Input at least 7 ticker symbols
- AI/ML-based directional modeling (Random Forest on technical features)
- Fundamental scoring using company financial metrics
- Sentiment scoring from financial headlines
- Buy/Hold/Sell recommendation per ticker with confidence score
- Interactive price trend chart (Close, SMA20, SMA50)
- Comprehensive per-ticker report view
- Downloadable consolidated reports in JSON or Markdown

## Tech Stack

- Backend: FastAPI + Python
- Data: yfinance + Yahoo finance RSS headlines
- ML: scikit-learn (RandomForestClassifier)
- Frontend: HTML/CSS/JavaScript + Chart.js

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start server:

```bash
uvicorn app.main:app --reload
```

4. Open browser:

- http://127.0.0.1:8000

## Notes

- This tool is educational and for research support only.
- Recommendations are model-generated signals and not financial advice.
- Model quality depends on data availability and market regime.
