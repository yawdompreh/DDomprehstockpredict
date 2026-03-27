const form = document.getElementById('analyze-form');
const tickersInput = document.getElementById('tickers');
const statusEl = document.getElementById('status');
const summaryGrid = document.getElementById('summary-grid');
const summaryText = document.getElementById('summary-text');
const reportsEl = document.getElementById('reports');
const tickerSelect = document.getElementById('ticker-select');
const downloadJsonBtn = document.getElementById('download-json');
const downloadMdBtn = document.getElementById('download-md');

let chart;
let latestSuccessful = [];

function parseTickers() {
  return tickersInput.value
    .split(',')
    .map((v) => v.trim().toUpperCase())
    .filter(Boolean)
    .filter((v, idx, arr) => arr.indexOf(v) === idx);
}

function signalClass(signal) {
  const normalized = signal.toLowerCase();
  if (normalized === 'buy') return 'buy';
  if (normalized === 'sell') return 'sell';
  return 'hold';
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? '#a42828' : '#3d5a61';
}

function renderSummary(results) {
  summaryGrid.innerHTML = '';

  for (const item of results) {
    const card = document.createElement('article');
    card.className = 'summary-card';

    if (item.status !== 'ok') {
      card.innerHTML = `
        <div class="ticker">${item.ticker}</div>
        <div class="signal sell">ERROR</div>
        <div class="report-meta">${item.error || 'Analysis failed'}</div>
      `;
      summaryGrid.appendChild(card);
      continue;
    }

    card.innerHTML = `
      <div class="ticker">${item.ticker}</div>
      <div class="signal ${signalClass(item.recommendation)}">${item.recommendation}</div>
      <div class="report-meta">Confidence: ${(item.confidence * 100).toFixed(1)}%</div>
      <div class="report-meta">Composite: ${item.composite_score.toFixed(3)}</div>
    `;
    summaryGrid.appendChild(card);
  }
}

function renderReports(results) {
  reportsEl.innerHTML = '';

  for (const item of results) {
    const div = document.createElement('article');
    div.className = 'report-item';

    if (item.status !== 'ok') {
      div.innerHTML = `
        <h3>${item.ticker}</h3>
        <div class="report-meta" style="color:#a42828">Analysis unavailable</div>
        <div class="report-content">${item.error || 'No details available'}</div>
      `;
      reportsEl.appendChild(div);
      continue;
    }

    const metrics = item.key_metrics || {};
    div.innerHTML = `
      <h3>${item.ticker} - ${metrics.company_name || ''}</h3>
      <div class="report-meta">
        Signal: <strong>${item.recommendation}</strong> |
        Confidence: ${(item.confidence * 100).toFixed(1)}% |
        Sector: ${metrics.sector || 'N/A'}
      </div>
      <details>
        <summary>Open full AI report</summary>
        <div class="report-content">${item.report_markdown}</div>
      </details>
    `;

    reportsEl.appendChild(div);
  }
}

function updateTickerSelector(successful) {
  tickerSelect.innerHTML = '';
  for (const item of successful) {
    const option = document.createElement('option');
    option.value = item.ticker;
    option.textContent = item.ticker;
    tickerSelect.appendChild(option);
  }
}

function renderChartForTicker(ticker) {
  const item = latestSuccessful.find((x) => x.ticker === ticker);
  if (!item) return;

  const ctx = document.getElementById('price-chart');
  const chartData = item.chart_data;

  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: chartData.dates,
      datasets: [
        {
          label: `${ticker} Close`,
          data: chartData.close,
          borderColor: '#1f6f8b',
          backgroundColor: 'rgba(31, 111, 139, 0.1)',
          borderWidth: 2,
          pointRadius: 0,
        },
        {
          label: 'SMA 20',
          data: chartData.sma20,
          borderColor: '#d3542a',
          borderWidth: 1.5,
          pointRadius: 0,
        },
        {
          label: 'SMA 50',
          data: chartData.sma50,
          borderColor: '#2a9d8f',
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          ticks: { maxTicksLimit: 12 },
        },
      },
      plugins: {
        legend: { position: 'top' },
      },
    },
  });
}

async function analyzeTickers(tickers) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Analysis request failed');
  }

  return response.json();
}

async function downloadReport(format, tickers) {
  const response = await fetch(`/api/report/download?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Download failed');
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = format === 'md' ? 'stock_reports.md' : 'stock_reports.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const tickers = parseTickers();
  if (tickers.length < 7) {
    setStatus('Enter at least 7 unique tickers.', true);
    return;
  }

  setStatus('Running AI model, sentiment scanner, and financial scoring...');
  summaryText.textContent = 'Analysis in progress...';
  downloadJsonBtn.disabled = true;
  downloadMdBtn.disabled = true;

  try {
    const data = await analyzeTickers(tickers);
    renderSummary(data.results);
    renderReports(data.results);

    latestSuccessful = data.results.filter((item) => item.status === 'ok');

    if (latestSuccessful.length > 0) {
      updateTickerSelector(latestSuccessful);
      renderChartForTicker(latestSuccessful[0].ticker);
      downloadJsonBtn.disabled = false;
      downloadMdBtn.disabled = false;
    }

    summaryText.textContent = `${data.completed} of ${data.requested} tickers analyzed successfully.`;
    setStatus('Analysis complete. Review signals and download reports.');
  } catch (err) {
    setStatus(err.message || 'Unexpected error during analysis.', true);
  }
});

tickerSelect.addEventListener('change', () => {
  renderChartForTicker(tickerSelect.value);
});

downloadJsonBtn.addEventListener('click', async () => {
  try {
    const tickers = parseTickers();
    await downloadReport('json', tickers);
    setStatus('JSON report downloaded successfully.');
  } catch (err) {
    setStatus(err.message || 'Could not download JSON report.', true);
  }
});

downloadMdBtn.addEventListener('click', async () => {
  try {
    const tickers = parseTickers();
    await downloadReport('md', tickers);
    setStatus('Markdown report downloaded successfully.');
  } catch (err) {
    setStatus(err.message || 'Could not download Markdown report.', true);
  }
});
