import os
import json
import boto3
from datetime import date, datetime, timedelta

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DDB_TABLE_NAME', 'spa_reservations'))


def handle_event(event, context):
    http_method = event.get('action', 'GET')

    if http_method == 'GET':
        return get_availability(event)
    elif http_method == 'POST':
        return create_booking(event)
    else:
        return {'statusCode': 400,
                'body': json.dumps('Unsupported HTTP method')}

def _get_available_slots(day: date):
    response = table.get_item(Key={'date': day.isoformat()})

    if 'Item' not in response:
        # If no reservations exist for this date, all slots are available
        available_slots = generate_all_slots()
    else:
        reserved_slots = response['Item'].get('reservations', {})
        available_slots = [slot for slot in generate_all_slots() if slot not in reserved_slots]

    return available_slots

def get_availability(event):
    day = event.get('queryStringParameters', {}).get('date',
                                                     (date.today() + timedelta(days=1)).isoformat())

    if not day:
        return {'statusCode': 400,
                'body': json.dumps('Date parameter is required')}
    try:
        # Validate date format
        day = datetime.strptime(day, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return {'statusCode': 400,
                'body': json.dumps('Invalid date format. Use YYYY-MM-DD')}

    return {'statusCode': 200,
            'body': {'response_type': 'spa_availability',
                     'date': day.isoformat(),
                     'available_slots': _get_available_slots(day)}}


def create_booking(event):
    try:
        body = json.loads(event['body'])
        time_slot = body['time_slot']
        reservation_time = datetime.strptime(time_slot, '%Y-%m-%d %H:%M')
        day = datetime.strptime(time_slot, '%Y-%m-%d %H:%M').date()
        customer_name = body['customer_name']
    except (json.JSONDecodeError, KeyError):
        return {'statusCode': 400,
                'body': json.dumps('Invalid request body')}

    if time_slot not in _get_available_slots(day):
        return {'statusCode': 400,
                'body': json.dumps('Invalid time slot')}

    try:
        # Append the reservation to the DDB table
        response = table.get_item(Key={'date': day})
        reservations = response.get('Item', {}).get('reservations', {})
        reservations[time_slot] = customer_name
        table.put_item(Item={'date': day,
                             'reservations': reservations,
                             'expiration_date': int((reservation_time + timedelta(hours=1)).timestamp())})

        return {'statusCode': 200,
                'body': json.dumps('Booking created successfully')}
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return {'statusCode': 409,
                'body': json.dumps('This time slot is already booked')}


def generate_all_slots(day: date =  datetime.today().date()):
    """
    Generate a list with all the valid slots (as ISO-formatted strings) for a particular date
    """
    t0 = datetime(year=day.year, month=day.month, day=day.day)
    start_time = t0 + timedelta(days=1, hours=9)
    end_time = t0 + timedelta(days=1, hours=16)
    time_slots = []

    current_time = start_time
    while current_time < end_time:
        time_slots.append(current_time.strftime('%Y-%m-%d %H:%M'))
        current_time += timedelta(hours=1)

    return time_slots
