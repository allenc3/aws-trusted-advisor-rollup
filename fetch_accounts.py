import boto3
import os
import json

def get_account_ids():
    """
    Access DynamoDB table that stores information for all the AWS accounts. The
    name for the table is specified in the serverless.yml file under 'custom'.

    Pulls out the 'AccountId' and 'AccountName' values from the table as a list of
    dictionaries, and thus the dynamoDB table MUST include the two fields.

    *** IMPORTANT NOTICE ***
    If your AccountId and AccountName data is not stored in a DynamoDB table,
    fill in this function and make sure the return type is a list of
    dictionaries with the format as so:
    
        [{'AccountId': <val>, 'AccountName': <val>}, ]

    Returns
    -------
    list of dictionaries
        List contains dictionaries of keys 'AccountId' and 'Alias'
        Ex. [{'AccountId': <val>, 'AccountName': <val>}, ]

    """
    table_name = str(os.getenv('DYNAMO_NAME'))
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    result = table.scan(Select="SPECIFIC_ATTRIBUTES", ProjectionExpression=\
                        "AccountId, AccountName")["Items"]

    return result

# Entry point for cron event
def handler(event=None, context=None):
    """
    Retrieves AccountId and AccountName information and sends them to AWS SQS.
    The queue name is specified in the serverless.yml file under 'custom'.

    The queue is used to distribute the workload to several different instances
    of the same lambda function. This allows processing accounts in paralell,
    and thus a faster computation time.
    """

    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.' + str(os.getenv('REGION')) + '.amazonaws.com/' \
                + str(os.getenv('ACCOUNT_ID')) + '/' + str(os.getenv('QUEUE_NAME'))

    print('Starting trusted advisor batch check process')
    accounts = get_account_ids()

    print('Fetched {} account ids'.format(len(accounts)))

    for account in accounts:
        try:
            response = sqs.send_message(
                QueueUrl=queue_url,
                DelaySeconds=10,
                MessageAttributes={
                    'AccountId': {
                        'StringValue': account['AccountId'],
                        'DataType': 'String'
                    },
                    'AccountName': {
                        'StringValue': account['AccountName'],
                        'DataType': 'String'
                    },
                },
                MessageBody='Sending account for processing'
            )

            print('Sent message to {}'.format(account['AccountId']), response)

        except Exception as e:
            print('Error sending SQS message to account_id: {id} account_name: {name}'.format(
                id=account['AccountId'], name=account['AccountName']))
            print(e)

    print('Batch sending process complete')

if __name__ == '__main__':
    handler()
