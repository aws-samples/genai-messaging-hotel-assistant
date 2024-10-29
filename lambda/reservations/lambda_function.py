import os
import json
import boto3
from datetime import date, datetime, timedelta

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DDB_TABLE_NAME', 'spa_reservations'))


def handle_event(event, context):
    if 'flow' in event:
        return get_availability(event)
    elif 'request_type' in event and event['request_type'] == 'booking_request':
        return create_booking(event)
    else:
        return {'statusCode': 400,
                'body': json.dumps('Unsupported HTTP method')}


def _get_available_slots(day: date):
    response = table.get_item(Key={'date': day.isoformat()})

    if 'Item' not in response:
        # If no reservations exist for this date, all slots are available
        available_slots = generate_all_slots(day)
    else:
        reserved_slots = response['Item'].get('reservations', {})
        available_slots = [slot for slot in generate_all_slots(day) if slot not in reserved_slots]

    # If there are no available slots, try the following day
    if len(available_slots) < 3:
        return available_slots + _get_available_slots(day=day + timedelta(days=1))

    return available_slots


def get_availability(event):
    try:
        day = event['node']['inputs'][0]['value']
    except (KeyError, IndexError):
        day = (date.today() + timedelta(days=1)).isoformat()

    try:
        # Validate date format
        day = datetime.strptime(day, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return {'statusCode': 400,
                'body': json.dumps('Invalid date format. Use ISO 8601 (YYYY-MM-DD)')}

    return {'statusCode': 200,
            'body': {'response_type': 'spa_availability',
                     'date': day.isoformat(),
                     'available_slots': _get_available_slots(day)}}


def create_booking(event):
    try:
        time_slot = event['time_slot']
        reservation_time = datetime.strptime(time_slot, '%Y-%m-%d %H:%M')
        day = reservation_time.date()
        customer_id = event['customer_id']
    except KeyError:
        return {'statusCode': 400,
                'body': json.dumps('Invalid request body')}

    if time_slot not in _get_available_slots(day):
        return {'statusCode': 400,
                'body': json.dumps('Invalid time slot')}

    try:
        # Append the reservation to the DDB table
        response = table.get_item(Key={'date': day.isoformat()})
        reservations = response.get('Item', {}).get('reservations', {})
        reservations[time_slot] = customer_id
        # Determine the maximum TTL that we should apply to this day, then register the booking
        ttl = max([int(datetime.strptime(ttl, '%Y-%m-%d %H:%M').timestamp()) for ttl in reservations.keys()])
        table.put_item(Item={'date': day.isoformat(),
                             'reservations': reservations,
                             'expiration_date': ttl})

        return {'statusCode': 200,
                'body': json.dumps('Booking created successfully')}
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return {'statusCode': 409,
                'body': json.dumps('This time slot is already booked')}


def generate_all_slots(day: date = date.today()):
    """
    Generate a list with all the valid slots (as ISO-formatted strings) for a particular date
    """
    t0 = datetime(year=day.year, month=day.month, day=day.day)
    start_time = t0 + timedelta(hours=9)
    end_time = t0 + timedelta(hours=16)
    time_slots = []

    current_time = start_time
    while current_time < end_time:
        if current_time >= datetime.now() + timedelta(minutes=10):
            time_slots.append(current_time.strftime('%Y-%m-%d %H:%M'))
        current_time += timedelta(hours=1)

    return time_slots


if __name__ == '__main__':
   create_booking({'time_slot': '2024-10-30 10:00',
                   'customer_id': '1234'})
