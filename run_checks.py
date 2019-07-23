import boto3
import time
from decimal import Decimal
from utils import assume_role_wrapper
import csv
import os

def get_all_checks(support_session, fail_msg):
    """
    Gets all the checks currently available in AWS Trusted Advisor.

    This is used to retrieve the check_ids, which will later be used to retrieve
    the result of all the checks.

    Parameters
    ----------
    support_session : boto3.session.Session.client('support')
        A support session for the targetted account.
    fail_msg: str
        Message to log error on CloudWatch

    Returns
    -------
    all_checks: dictionary of dictionaries
        A dictionary that uses check_id as the key, and contains another
        dictoinary as the value. The value contains the name and category of the
        check.
    """

    try:
        checks = support_session.describe_trusted_advisor_checks(language='en')
    except Exception as e:
        print('{}  Error: {}'.format(fail_msg, str(e)))
        return None

    all_checks = {}
    for check in checks['checks']:
        all_checks[check['id']] = {
            'name': check['name'],
            'category': check['category']
        }

    return all_checks

def get_check_summary(support_session, check_ids, fail_msg):
    """
    Gets the check result for each check included in check_ids.

    Returns a list of check results specifying the 'estimated_monthly_savings'
    and 'status' of all the check_ids.

    Parameters
    ----------
    support_session : boto3.session.Session.client('support')
        A support session for the targetted account.
    check_ids: list of str
        A list containing all the check_ids
    fail_msg: str
        Message to log error on CloudWatch

    Returns
    -------
    check_result: list of dictionaries
        A list of dictionaries that contains the 'estimated_monthly_savings'
        and 'status' of all the checks.
    """
    try:
        summary = support_session.describe_trusted_advisor_check_summaries(checkIds=check_ids)
        check_results = []
        for check in summary['summaries']:
            check_result = {
                'status': check['status']
            }
            if 'categorySpecificSummary' in check and 'costOptimizing' in check['categorySpecificSummary'] and 'estimatedMonthlySavings' in check['categorySpecificSummary']['costOptimizing']:
                TWOPLACES = Decimal(10) ** -2
                check_result['estimated_monthy_savings'] = Decimal(check['categorySpecificSummary']['costOptimizing']['estimatedMonthlySavings']).quantize(TWOPLACES)
            else:
                check_result['estimated_monthy_savings'] = 0

            check_results.append(check_result)

        return check_results
    except Exception as e:
        print('{}  Error: {}'.format(fail_msg, str(e)))
        return None

def file_exists_in_s3(s3_session, file_name):
    """
    Checks if file exists in s3 already.

    As our AWS SQS queue is a standard queue, messages may be sent multiple
    time, and thus accounts could be processed multiple times. To prevent this,
    check if the intended file to upload already exists. The desired response
    is for get_object to return an error, since that means the file doesn't
    exist.

    Parameters
    ----------
    s3_session : boto3.session.Session.client('s3')
        An s3 session
    file_name: str
        file_name to search for in s3 bucket.

    Returns
    -------
    True if file exists, False if not.
    """
    bucket_name = str(os.getenv('BUCKET_NAME'))
    try:
        response = s3_session.get_object(
            Bucket=bucket_name,
            Key=file_name,
        )

    except Exception as e:
        return False

    return True

def sts_session():
    """
    Wrapper to get access to sts services from starting account.

    Returns
    -------
    session: boto3.session.Session.client('sts')
        Returns a sts session from the targetted account.
    """
    try:
        return boto3.client('sts')
    except Exception as e:
        print('Current IAM role does not have the permission to use STS service.')
        return None

def s3_session():
    """
    Wrapper to get access to s3 services from starting account.

    Returns
    -------
    session: boto3.session.Session.client('s3')
        Returns a s3 session from the targetted account.
    """
    try:
        return boto3.client('s3')
    except Exception as e:
        print('Current IAM role does not have the permission to use S3 service.')
        return None

def support_session(target_session, target_account_name):
    """
    Wrapper to get access to support services from targetted account.

    Parameters
    ----------
    target_session : boto3.session.Session
        An session of the targetted account that will be used to access support.
    target_account_name: str
        For logging and naming purposes.

    Returns
    -------
    session: boto3.session.Session.client('support')
        Returns a support session as the base_iam_role of the targetted account.
    """
    try:
        return target_session.client('support')
    except Exception as e:
        print('Base IAM role in {} does not have access to support.'.format(target_account_name))
        return None

def uploaded_to_s3(file_name, fail_msg):
    """
    Uploads the results in /tmp/data.csv to the s3 bucket. Within the bucket,
    dates with the format 'YYYY-MM-DD' are used as the folder name, and each
    folder will include csv files summarizing Trusted Advisor data for each account.

    Parameters
    ----------
    file_name : str
        Filename used to store the file in the s3 bucket.
    fail_msg: str
        For logging purposes.

    Returns
    -------
    True if successfully uploaded, false if not
    """
    try:
        bucket_name = str(os.getenv('BUCKET_NAME'))
        s3 = boto3.resource('s3')
        s3.Bucket(bucket_name).upload_file('/tmp/data.csv', file_name)
        return True
    except Exception as e:
        print('{} Trusted Advisor results could not be uploaded to {}. Error: {}'.format(fail_msg, bucket_name, e))
        return False


def handler(event, context):
    """
    Calls assume_role to switch into the targetted account based on the event
    parameter. Then stores the Trusted Advisor data result in a local csv file,
    and finally uploads the result to s3.
    """
    target_account_id = event['Records'][0]['messageAttributes']['AccountId']['stringValue']
    target_account_name = event['Records'][0]['messageAttributes']['AccountName']['stringValue']
    base_iam_role = str(os.getenv('BASE_ROLE'))
    fail_msg = 'Pulling Trusted Advisor data from {} failed.'.format(target_account_name)

    starting_session_sts = sts_session()
    if starting_session_sts == None:
        return

    starting_session_s3 = s3_session()
    if starting_session_s3 == None:
        return

    time_int = int(time.time())
    offset = time_int % (24*3600)
    time_str = time.strftime("%Y-%m-%d", time.gmtime(time_int - offset))
    time_int = int(time.strftime("%Y%m%d", time.gmtime(time_int - offset)))

    file_name = time_str + '/' + target_account_name + '.csv'

    if file_exists_in_s3(starting_session_s3, file_name):
        print('Account has been processed already.')
        return

    # After checking if the file exists, switch into the target account and pull
    # Trusted Advisor data.
    target_session = assume_role_wrapper(starting_session_sts, target_account_id, target_account_name, base_iam_role, fail_msg)
    if target_session == None:
        return

    target_session_support = support_session(target_session, target_account_name)
    if target_session_support == None:
        return

    all_checks = get_all_checks(target_session_support, fail_msg)
    if all_checks == None:
        return

    check_results = get_check_summary(target_session_support, list(all_checks.keys()), fail_msg)
    if check_results == None:
        return

    # Starts constructing a list of dictionaries in order to create a csv file.
    check_list = []
    for result, check in zip(check_results, all_checks.items()):
        # check = (check_id, {category: <val>, name: <val>})
        check_list.append({
            'date': time_int,
            'account_id': target_account_id,
            'status': result['status'],
            'category': check[1]['category'],
            'check_id': check[0],
            'check_name': check[1]['name'],
            'estimated_monthy_saving': result['estimated_monthy_savings'],
            'account_name': target_account_name
        })

    """
    *** IMPORTANT***
    Need to use /tmp/ since that is the folder where AWS lambda functions are
    allowed to create temporary files.
    """
    with open('/tmp/data.csv', 'w') as file:
        w = csv.DictWriter(file, check_list[0].keys())
        w.writeheader()
        for check_results in check_list:
            w.writerow(check_results)

    # Upload to S3 bucket.
    if uploaded_to_s3(file_name, fail_msg):
        print("Success! Account name: {}".format(target_account_name))

if __name__ == '__main__':
    handler()
