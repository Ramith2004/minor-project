@echo off
echo Setting up Python virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo Virtual environment created and dependencies installed.
echo.
echo ===========================================
echo MQTT Broker Setup for Windows:
echo ===========================================
echo.
echo 1. Download and install Mosquitto MQTT broker:
echo    Visit: https://mosquitto.org/download/
echo    Download the Windows installer (.exe file)
echo.
echo 2. After installation, add Mosquitto to your PATH:
echo    Add C:\Program Files\mosquitto to your system PATH
echo.
echo 3. To start MQTT broker, run in a new Command Prompt:
echo    mosquitto -v
echo.
echo 4. To check if MQTT is running:
echo    mosquitto_pub -h localhost -t test -m "hello"
echo    mosquitto_sub -h localhost -t test
echo.
echo
echo ===========================================
echo Setup completed! Next steps:
echo ===========================================
echo 1. Install and start MQTT broker (see above)
echo 2. Activate virtual environment: venv\Scripts\activate.bat
echo 3. Start IDS service: python ids/ids_service.py
echo 4. Start backend: python backend/app.py
echo 5. Create meter keys: python meters/key_manager.py init --meters meter_000,meter_001
echo 6. Start meters: python meters/multi_meter_sim.py --meters meter_000,meter_001
echo.
pause