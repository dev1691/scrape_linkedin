# 🔍 LinkedIn Resume Scraper API

A FastAPI-based web scraper that searches LinkedIn profiles and detects resume attachments using Selenium automation with parallel processing.

## 🌟 Features

- 🔐 **Automated LinkedIn Login** - Secure authentication with environment variables
- 🔎 **Smart Search** - Search for profiles using custom queries
- 🧵 **Parallel Processing** - Multi-threaded profile checking (up to 6 workers)
- 📄 **Resume Detection** - Heuristic detection of PDF/DOCX resume attachments
- 💾 **CSV Export** - Automatic export of results with timestamps
- 📊 **Rotating Logs** - Comprehensive logging with automatic rotation (5MB limit)
- 🚀 **RESTful API** - Simple HTTP endpoints for integration

## 🛠️ Tech Stack

- **Framework**: FastAPI
- **Automation**: Selenium WebDriver
- **Browser**: Chrome/Chromium (headless mode)
- **Concurrency**: ThreadPoolExecutor
- **Data Export**: Pandas (CSV)
- **Logging**: Python logging with RotatingFileHandler

## 📋 Prerequisites

- Python 3.8+
- Chrome/Chromium browser
- ChromeDriver (matching browser version)
- LinkedIn account with valid credentials

## 🚀 Installation

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd linkedin-scraper
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**
```
fastapi
uvicorn
selenium
webdriver-manager
python-dotenv
pandas
pydantic
```

### 3. Setup Environment

Create `.env` file:

```bash
# LinkedIn Credentials (Required)
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Browser Settings
HEADLESS=true
CHROME_BIN=/usr/bin/chromium
CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Output Directories
OUTPUT_DIR=/app/output
LOG_DIR=/app/logs
```

### 4. Install Chrome/Chromium

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y chromium chromium-driver
```

**macOS:**
```bash
brew install chromium chromedriver
```

## 🎯 Usage

### Start the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Server will start at: `http://localhost:8000`

### API Documentation

Interactive docs available at: `http://localhost:8000/docs`

### Make a Search Request

**Endpoint:** `POST /search`

**Request Body:**
```json
{
  "query": "Software Engineer",
  "max_profiles": 20
}
```

**Example with cURL:**
```bash
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Data Scientist",
    "max_profiles": 30
  }'
```

**Example with Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/search",
    json={
        "query": "Machine Learning Engineer",
        "max_profiles": 25
    }
)

print(response.json())
```

**Response:**
```json
{
  "status": "completed",
  "query": "Software Engineer",
  "profiles_checked": 20,
  "resumes_found": 7,
  "csv_path": "/app/output/results_Software_Engineer_20250107T143052Z.csv",
  "results_preview": [
    {
      "profile_url": "https://linkedin.com/in/johndoe",
      "resume_found": true,
      "resume_links": ["https://example.com/resume.pdf"],
      "error": null
    }
  ]
}
```

## 📊 Output

### CSV File Structure

Results are saved to `OUTPUT_DIR` with the following columns:

| Column | Description |
|--------|-------------|
| `profile_url` | LinkedIn profile URL |
| `resume_found` | Boolean (True if resume detected) |
| `resume_links` | List of detected resume/document links |
| `error` | Error message if profile check failed |

**Example CSV:**
```csv
profile_url,resume_found,resume_links,error
https://linkedin.com/in/johndoe,True,"['resume.pdf']",
https://linkedin.com/in/janedoe,False,[],
https://linkedin.com/in/bobsmith,True,"['cv.docx', 'resume.pdf']",
```

### Log Files

Logs are stored in `LOG_DIR/app.log` with rotation:
- Max file size: 5MB
- Backup count: 5 files
- Format: `2025-01-07 14:30:52 [INFO] linkedin_scraper - Message`

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LINKEDIN_EMAIL` | *Required* | LinkedIn account email |
| `LINKEDIN_PASSWORD` | *Required* | LinkedIn account password |
| `HEADLESS` | `true` | Run browser in headless mode |
| `CHROME_BIN` | `/usr/bin/chromium` | Path to Chrome/Chromium binary |
| `CHROMEDRIVER_PATH` | `/usr/bin/chromedriver` | Path to ChromeDriver executable |
| `OUTPUT_DIR` | `/app/output` | Directory for CSV output |
| `LOG_DIR` | `/app/logs` | Directory for log files |

### Performance Tuning

**Adjust parallel workers** (in `app.py`):
```python
MAX_WORKERS = 6  # Increase for more parallelism (CPU/memory dependent)
```

**Adjust timeouts** (in `app.py`):
```python
timeout=15  # WebDriver wait timeout (seconds)
```

**Scroll behavior** (in `search_and_collect_profiles`):
```python
scroll_tries < 30  # Maximum scroll attempts
```

## 🏗️ Architecture

```
┌─────────────┐
│  FastAPI    │  POST /search
│  Endpoint   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Primary    │  Login & Search
│  Driver     │  Collect URLs
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│  ThreadPoolExecutor     │
│  (6 parallel workers)   │
└────┬────┬────┬────┬─────┘
     │    │    │    │
     ▼    ▼    ▼    ▼
   [Driver instances]
   Login → Visit → Check → Quit
     │
     ▼
┌─────────────┐
│  Aggregate  │  Combine results
│  Results    │  Export to CSV
└─────────────┘
```

## 🔍 Resume Detection Logic

The scraper uses heuristic pattern matching:

1. **Page Source Search** - Scans HTML for keywords:
   - File extensions: `.pdf`, `.docx`, `.doc`
   - Keywords: `resume`, `cv` (case-insensitive)

2. **Link Extraction** - Finds anchor tags with:
   - Document file extensions in `href`
   - Text content containing resume/CV keywords

3. **Deduplication** - Removes duplicate links

**Regex Pattern:**
```python
RESUME_REGEX = re.compile(r"\.pdf|\.docx|\.doc|resume|cv", re.IGNORECASE)
```

## ⚠️ Important Notes

### LinkedIn Terms of Service

**⚠️ WARNING**: Web scraping may violate LinkedIn's Terms of Service. Use responsibly:
- Only scrape publicly available information
- Respect rate limits and delays
- Use for personal/research purposes only
- Consider LinkedIn's official API for commercial use

### Rate Limiting

The scraper includes built-in delays:
- Random delays between requests (0.7-1.5s)
- Polite delays after page loads (1.5-2.5s)
- Scroll delays (1-1.5s)

**Recommended:**
- Don't run continuous scraping
- Limit to 20-50 profiles per session
- Add longer delays for production use

### Anti-Detection Measures

Built-in measures:
- Custom user-agent string
- `webdriver` property masking
- Random timing variations
- No automation flags in browser

### Account Safety

- Use a dedicated LinkedIn account for scraping
- Enable 2FA on your primary account
- Monitor for unusual activity notifications
- Consider rotating IP addresses

## 🐛 Troubleshooting

### ChromeDriver Version Mismatch

**Error:** `SessionNotCreatedException: session not created: This version of ChromeDriver only supports Chrome version X`

**Fix:**
```bash
# Check Chrome version
chromium --version

# Download matching ChromeDriver
# From: https://chromedriver.chromium.org/downloads

# Update CHROMEDRIVER_PATH in .env
```

### Login Failures

**Error:** `RuntimeError: Login didn't complete — possible 2FA or blocking`

**Solutions:**
1. Disable 2FA on scraping account
2. Use account without security challenges
3. Manual login first to verify credentials
4. Check if LinkedIn flagged account

### Search Input Not Found

**Error:** `Search input not found after login`

**Fix:** LinkedIn may have changed selectors
```python
# Update SEARCH_XPATH in app.py
SEARCH_XPATH = "/html/body/div[5]/header/div/div/div/div[1]/input"
```

### Timeout Errors

Increase timeout values:
```python
# In login_linkedin(), search_and_collect_profiles(), detect_resume_worker()
timeout=20  # Increase from default 15
```

### No Results Found

**Possible causes:**
- Query too specific
- Region restrictions
- LinkedIn algorithm changes
- Network issues

**Solutions:**
- Try broader queries
- Check logs for errors
- Verify manual search works
- Add longer delays

## 📈 Performance

### Benchmarks

- **Single profile check**: ~3-5 seconds
- **20 profiles** (6 workers): ~15-25 seconds
- **50 profiles** (6 workers): ~40-60 seconds

### Resource Usage

- **CPU**: ~20-30% per worker (total 120-180%)
- **Memory**: ~200MB per browser instance
- **Network**: ~5-10 Mbps during active scraping

### Scaling

**Vertical (single machine):**
```python
MAX_WORKERS = 10  # More workers (requires more RAM)
```

**Horizontal (distributed):**
- Deploy multiple API instances
- Use load balancer
- Rotate LinkedIn accounts
- Implement queue system (Celery/RQ)

## 🔐 Security Best Practices

1. **Never commit `.env` file**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use environment variables in production**
   ```bash
   export LINKEDIN_EMAIL="email@example.com"
   export LINKEDIN_PASSWORD="secure_password"
   ```

3. **Rotate credentials regularly**

4. **Run in isolated environment** (Docker/VM)

5. **Monitor LinkedIn account for suspicious activity**

## 🐳 Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN mkdir -p /app/output /app/logs

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  linkedin-scraper:
    build: .
    ports:
      - "8000:8000"
    environment:
      - LINKEDIN_EMAIL=${LINKEDIN_EMAIL}
      - LINKEDIN_PASSWORD=${LINKEDIN_PASSWORD}
      - HEADLESS=true
    volumes:
      - ./output:/app/output
      - ./logs:/app/logs
```

**Run:**
```bash
docker-compose up --build
```

## 📝 Future Enhancements

- [ ] Support for other LinkedIn search filters (location, company, etc.)
- [ ] Download and store resume files
- [ ] Add authentication to API endpoints
- [ ] Implement job queue for async processing
- [ ] Add webhook notifications on completion
- [ ] Support multiple LinkedIn accounts
- [ ] Implement proxy rotation
- [ ] Add UI dashboard for monitoring
- [ ] Export to multiple formats (JSON, Excel)
- [ ] Detailed profile data extraction (name, title, company)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

MIT License - see LICENSE file for details

## ⚖️ Legal Disclaimer

This tool is for educational and research purposes only. Users are responsible for:
- Complying with LinkedIn's Terms of Service
- Respecting data privacy laws (GDPR, CCPA, etc.)
- Obtaining necessary permissions for data collection
- Using scraped data ethically and legally

The authors are not responsible for misuse of this tool.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Selenium](https://www.selenium.dev/) - Browser automation
- [Pandas](https://pandas.pydata.org/) - Data manipulation
- [webdriver-manager](https://github.com/SergeyPirogov/webdriver_manager) - Driver management

## 📞 Support

For issues or questions:
1. Check troubleshooting section
2. Review logs in `/app/logs/app.log`
3. Open an issue on GitHub

---

**Use Responsibly!** 🚀🔍📊