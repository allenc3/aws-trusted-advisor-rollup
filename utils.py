import boto3

def assume_role_wrapper(sts_session, target_account_id, target_account_name, base_iam_role, fail_msg):
    """
    Tries to call the assume_role function to switch into another role in the
    targetted account.

    Assume-role requires two steps:
        1). lambda execution role running the current function must have write
            access to STS (can be checked in the IAM console).
        2). target_account must have a trusted relationship with the starting
            account (account where the current lambda function is running on).
            The trusted relationships an account has can be found on the IAM
            console as well.

    Parameters
    ----------
    sts_session : boto3.session.Session.client('sts')
        An sts session
    target-account_id : str
        AccountId of the targetted account. Can be found in the IAM console.
    target_account_name: str
        For logging and naming purposes.
    base_iam_role: str
        The name of the IAM role that should be propagated into all AWS
        accounts. This role should have read access to Support (IAM console).
    fail_msg: str
        Message to log error on CloudWatch


    Returns
    -------
    session: boto3.Session
        Returns a session as the base_iam_role of the targetted account.

    """
    arn = "arn:aws:iam::" + target_account_id + ":role/" + base_iam_role
    try:
        assume = sts_session.assume_role(
            RoleArn=arn,
            RoleSessionName="AssumedRoleSession")

    except Exception as e:
        print('{} Could not switch account into the {} role of {} . Error: {}'.format(fail_msg, base_iam_role, target_account_name, str(e)))
        return None

    tempcreds = assume["Credentials"]
    session = boto3.Session(
        aws_access_key_id=tempcreds["AccessKeyId"],
        aws_secret_access_key=tempcreds["SecretAccessKey"],
        aws_session_token=tempcreds["SessionToken"])

    return session
