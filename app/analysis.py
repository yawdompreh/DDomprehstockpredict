from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import feedparser
import numpy as np
import pandas as pd
import yfinance as yf
from nltk.sentiment import SentimentIntensityAnalyzer
from sklearn.ensemble import RandomForestClassifier


@dataclass
class AnalysisResult:
    ticker: str
    recommendation: str
    confidence: float
    composite_score: float
    technical_score: float
    fundamental_score: float
    sentiment_score: float
    prediction_probability_up: float
    key_metrics: Dict[str, Any]
    chart_data: Dict[str, Any]
    report_markdown: str


class StockAnalyzer:
    def __init__(self) -> None:
        self._sentiment = self._create_sentiment_engine()

    @staticmethod
    def _create_sentiment_engine() -> SentimentIntensityAnalyzer:
        try:
            return SentimentIntensityAnalyzer()
        except LookupError:
            import nltk

            nltk.download("vader_lexicon", quiet=True)
            return SentimentIntensityAnalyzer()

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        avg_gain = up.rolling(window=period, min_periods=period).mean()
        avg_loss = down.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _macd(series: pd.Series) -> pd.DataFrame:
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        return pd.DataFrame({"macd": macd, "signal": signal, "hist": hist})

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        data["return_1d"] = data["Close"].pct_change()
        data["return_5d"] = data["Close"].pct_change(5)
        data["volatility_10d"] = data["return_1d"].rolling(10).std()
        data["sma_20"] = data["Close"].rolling(20).mean()
        data["sma_50"] = data["Close"].rolling(50).mean()
        data["rsi"] = self._rsi(data["Close"])

        macd = self._macd(data["Close"])
        data = data.join(macd)

        data["target_up"] = (data["Close"].shift(-1) > data["Close"]).astype(int)
        return data.dropna().copy()

    @staticmethod
    def _score_fundamentals(info: Dict[str, Any]) -> float:
        score = 0.5

        revenue_growth = info.get("revenueGrowth")
        if revenue_growth is not None:
            score += np.clip(revenue_growth, -0.4, 0.6) * 0.3

        profit_margin = info.get("profitMargins")
        if profit_margin is not None:
            score += np.clip(profit_margin, -0.2, 0.4) * 0.25

        roe = info.get("returnOnEquity")
        if roe is not None:
            score += np.clip(roe, -0.2, 0.6) * 0.2

        debt_to_equity = info.get("debtToEquity")
        if debt_to_equity is not None:
            debt_penalty = min(max((debt_to_equity - 100) / 300, -0.2), 0.3)
            score -= debt_penalty

        trailing_pe = info.get("trailingPE")
        if trailing_pe is not None and trailing_pe > 0:
            pe_center = 22
            pe_spread = 20
            valuation_component = 1 - min(abs(trailing_pe - pe_center) / pe_spread, 1)
            score += (valuation_component - 0.5) * 0.1

        return float(np.clip(score, 0.0, 1.0))

    def _score_sentiment(self, ticker: str) -> float:
        feed_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        parsed = feedparser.parse(feed_url)

        headlines = [entry.get("title", "") for entry in parsed.entries[:20]]
        if not headlines:
            return 0.5

        compounds = [self._sentiment.polarity_scores(headline)["compound"] for headline in headlines]
        avg_compound = float(np.mean(compounds))
        normalized = (avg_compound + 1) / 2
        return float(np.clip(normalized, 0.0, 1.0))

    @staticmethod
    def _label_from_score(score: float) -> str:
        if score >= 0.62:
            return "BUY"
        if score <= 0.45:
            return "SELL"
        return "HOLD"

    def analyze_ticker(self, ticker: str) -> AnalysisResult:
        tk = ticker.strip().upper()
        if not tk:
            raise ValueError("Ticker cannot be empty")

        yf_ticker = yf.Ticker(tk)
        history = yf_ticker.history(period="2y", interval="1d", auto_adjust=True)
        if history.empty or len(history) < 120:
            raise ValueError(f"Not enough historical data for {tk}")

        features = self._prepare_features(history)
        if len(features) < 80:
            raise ValueError(f"Not enough valid feature rows for {tk}")

        feature_cols = [
            "return_1d",
            "return_5d",
            "volatility_10d",
            "sma_20",
            "sma_50",
            "rsi",
            "macd",
            "signal",
            "hist",
            "Volume",
        ]

        split = int(len(features) * 0.8)
        train_df = features.iloc[:split]

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=3,
            random_state=42,
        )
        model.fit(train_df[feature_cols], train_df["target_up"])

        last_row = features.iloc[[-1]]
        proba_up = float(model.predict_proba(last_row[feature_cols])[0][1])

        info = yf_ticker.info or {}
        fundamental_score = self._score_fundamentals(info)
        sentiment_score = self._score_sentiment(tk)

        rsi = float(last_row["rsi"].iloc[0])
        macd_hist = float(last_row["hist"].iloc[0])
        technical_boost = 0.0

        if rsi < 30:
            technical_boost += 0.06
        elif rsi > 70:
            technical_boost -= 0.06

        if macd_hist > 0:
            technical_boost += 0.04
        else:
            technical_boost -= 0.04

        technical_score = float(np.clip(proba_up + technical_boost, 0.0, 1.0))

        composite_score = (
            technical_score * 0.45 + fundamental_score * 0.3 + sentiment_score * 0.25
        )

        recommendation = self._label_from_score(composite_score)
        confidence = float(np.clip(abs(composite_score - 0.5) * 2, 0.05, 0.99))

        recent = history.tail(180).copy()
        recent["sma_20"] = recent["Close"].rolling(20).mean()
        recent["sma_50"] = recent["Close"].rolling(50).mean()

        key_metrics = {
            "company_name": info.get("shortName", tk),
            "sector": info.get("sector"),
            "market_cap": info.get("marketCap"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "roe": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_price": float(recent["Close"].iloc[-1]),
            "rsi": round(rsi, 2),
            "model_up_probability": round(proba_up, 4),
        }

        chart_data = {
            "dates": [d.strftime("%Y-%m-%d") for d in recent.index.to_pydatetime()],
            "close": [float(v) for v in recent["Close"].tolist()],
            "volume": [int(v) for v in recent["Volume"].fillna(0).tolist()],
            "sma20": [None if np.isnan(v) else float(v) for v in recent["sma_20"].values],
            "sma50": [None if np.isnan(v) else float(v) for v in recent["sma_50"].values],
        }

        report_markdown = self._build_report_markdown(
            ticker=tk,
            recommendation=recommendation,
            confidence=confidence,
            composite_score=composite_score,
            technical_score=technical_score,
            fundamental_score=fundamental_score,
            sentiment_score=sentiment_score,
            key_metrics=key_metrics,
        )

        return AnalysisResult(
            ticker=tk,
            recommendation=recommendation,
            confidence=confidence,
            composite_score=float(composite_score),
            technical_score=float(technical_score),
            fundamental_score=float(fundamental_score),
            sentiment_score=float(sentiment_score),
            prediction_probability_up=proba_up,
            key_metrics=key_metrics,
            chart_data=chart_data,
            report_markdown=report_markdown,
        )

    @staticmethod
    def _build_report_markdown(
        ticker: str,
        recommendation: str,
        confidence: float,
        composite_score: float,
        technical_score: float,
        fundamental_score: float,
        sentiment_score: float,
        key_metrics: Dict[str, Any],
    ) -> str:
        generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        return (
            f"# {ticker} AI Equity Intelligence Report\\n\\n"
            f"Generated: {generated}\\n\\n"
            "## Executive Summary\\n"
            f"- Recommendation: **{recommendation}**\\n"
            f"- Confidence: **{confidence:.2%}**\\n"
            f"- Composite score: **{composite_score:.3f}** (0-1 scale)\\n\\n"
            "## Model Breakdown\\n"
            f"- Technical score: {technical_score:.3f}\\n"
            f"- Fundamental score: {fundamental_score:.3f}\\n"
            f"- Sentiment score: {sentiment_score:.3f}\\n\\n"
            "## Fundamental Snapshot\\n"
            f"- Company: {key_metrics.get('company_name')}\\n"
            f"- Sector: {key_metrics.get('sector')}\\n"
            f"- Current price: {key_metrics.get('current_price')}\\n"
            f"- Trailing P/E: {key_metrics.get('trailing_pe')}\\n"
            f"- Forward P/E: {key_metrics.get('forward_pe')}\\n"
            f"- Revenue growth: {key_metrics.get('revenue_growth')}\\n"
            f"- Profit margin: {key_metrics.get('profit_margin')}\\n"
            f"- Return on equity: {key_metrics.get('roe')}\\n"
            f"- Debt to equity: {key_metrics.get('debt_to_equity')}\\n\\n"
            "## Technical Snapshot\\n"
            f"- RSI (14): {key_metrics.get('rsi')}\\n"
            f"- ML next-day up probability: {key_metrics.get('model_up_probability')}\\n\\n"
            "## Interpretation\\n"
            "The recommendation combines machine-learned directional probability with valuation quality and current news sentiment. This output is a decision-support signal and not financial advice."
        )


analyzer = StockAnalyzer()


def analyze_many(tickers: List[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for ticker in tickers:
        try:
            item = analyzer.analyze_ticker(ticker)
            results.append(
                {
                    "ticker": item.ticker,
                    "recommendation": item.recommendation,
                    "confidence": item.confidence,
                    "composite_score": item.composite_score,
                    "technical_score": item.technical_score,
                    "fundamental_score": item.fundamental_score,
                    "sentiment_score": item.sentiment_score,
                    "prediction_probability_up": item.prediction_probability_up,
                    "key_metrics": item.key_metrics,
                    "chart_data": item.chart_data,
                    "report_markdown": item.report_markdown,
                    "status": "ok",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "ticker": ticker.strip().upper(),
                    "status": "error",
                    "error": str(exc),
                }
            )

    return results
