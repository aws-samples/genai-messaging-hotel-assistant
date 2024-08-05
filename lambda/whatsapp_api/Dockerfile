FROM public.ecr.aws/lambda/python:3.12

# Install required dependencies
WORKDIR ${LAMBDA_TASK_ROOT}
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the source code from the web image over here, that way we won't require
# installing composer in this image, too
COPY . .

# Define the lambda entrypoint
CMD [ "whatsapp_api.handler" ]
