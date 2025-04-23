# Use Python 3.6 as the base image for building the application.
# This image includes Python 3.6 and pip, which are necessary for running the application.
FROM python:3.6

# Set the working directory inside the container to /app
# All subsequent commands will be run from this directory.
WORKDIR /app

# Copy the requirements.txt file into the /app directory in the container
# This file contains the list of Python dependencies required by the application.
COPY requirements.txt requirements.txt

# Install the Python dependencies specified in requirements.txt
# This command uses pip to install the required packages into the container.
RUN pip3 install -r requirements.txt

# Copy the entire contents of the current directory (the application's source code) into the /app directory in the container
COPY . .

# Define the command to start the application
# This command will be executed when the container starts.
# It runs the `main.py` script using Python 3. The `-u` flag is used to run the Python interpreter in unbuffered mode, which can be useful for logging.
CMD [ "python3", "-u", "main.py" ]