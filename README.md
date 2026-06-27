# my_python

A small Python app that loads CSV data into a PostgreSQL table.

## Files
- [load_csv_to_postgres.py](load_csv_to_postgres.py): loads a CSV into PostgreSQL
- [sample_data.csv](sample_data.csv): sample input data
- [requirements.txt](requirements.txt): Python dependencies
- [db_config.json](db_config.json): PostgreSQL connection settings

## Run locally
1. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Edit [db_config.json](db_config.json) with your database details.
3. Run a dry run:
   ```bash
   python load_csv_to_postgres.py sample_data.csv --table users --create-table --dry-run --config db_config.json
   ```
4. Load into PostgreSQL:
   ```bash
   python load_csv_to_postgres.py sample_data.csv --table users --create-table --config db_config.json
   ```
