# Create a file named sample_leads.csv
Data Format :-company,first_name,email,segment,start_step,start_date

# Run the following command first to allow execution in terminal

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass


# After success run the following commands

deactivate
.\.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py