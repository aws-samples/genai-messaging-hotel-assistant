import json
import boto3
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('SpaReservations')


def lambda_handler(event, context):
    http_method = event['httpMethod']

    if http_method == 'GET':
        return get_availability(event)
    elif http_method == 'POST':
        return create_booking(event)
    else:
        return {
            'statusCode': 400,
            'body': json.dumps('Unsupported HTTP method')
        }


def get_availability(event):
    date = event['queryStringParameters'].get('date')

    if not date:
        return {
            'statusCode': 400,
            'body': json.dumps('Date parameter is required')
        }

    try:
        # Validate date format
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid date format. Use YYYY-MM-DD')
        }

    response = table.get_item(Key={'date': date})

    if 'Item' not in response:
        # If no reservations exist for this date, all slots are available
        available_slots = generate_all_slots()
    else:
        reserved_slots = response['Item'].get('reservations', {})
        available_slots = [slot for slot in generate_all_slots() if slot not in reserved_slots]

    return {
        'statusCode': 200,
        'body': json.dumps(available_slots)
    }


def create_booking(event):
    try:
        body = json.loads(event['body'])
        date = body['date']
        time_slot = body['time_slot']
        customer_name = body['customer_name']
    except (json.JSONDecodeError, KeyError):
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid request body')
        }

    try:
        # Validate date format
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid date format. Use YYYY-MM-DD')
        }

    if time_slot not in generate_all_slots():
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid time slot')
        }

    try:
        response = table.update_item(
            Key={'date': date},
            UpdateExpression='SET reservations.#ts = :val',
            ExpressionAttributeNames={'#ts': time_slot},
            ExpressionAttributeValues={':val': customer_name},
            ConditionExpression='attribute_not_exists(reservations.#ts)',
            ReturnValues='UPDATED_NEW'
        )

        return {
            'statusCode': 200,
            'body': json.dumps('Booking created successfully')
        }
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return {
            'statusCode': 409,
            'body': json.dumps('This time slot is already booked')
        }


def generate_all_slots():
    start_time = datetime.strptime('09:00', '%H:%M')
    end_time = datetime.strptime('17:00', '%H:%M')
    time_slots = []

    current_time = start_time
    while current_time < end_time:
        time_slots.append(current_time.strftime('%H:%M'))
        current_time += timedelta(hours=1)

    return time_slots
