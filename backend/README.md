# Kodiak Backend

## Setup
1.  Install dependencies:
    ```bash
    poetry install
    ```
2.  Run server:
    ```bash
    poetry run uvicorn main:app --reload
    ```

### Docker (Recommended)
You can run the entire stack (Backend + PostgreSQL) using Docker Compose:

```bash
docker-compose up --build
```
This solves dependencies like Nmap and Nuclei automatically.

## Structure
- `api/`: Routes
- `core/`: Logic
- `database/`: storage
- `services/`: external integrations
