# AWS Trusted Advisor Rollup

## Overview

AWS Trusted Advisor is an AWS service that monitors the health of an
account. However, Trusted Advisor is only offered per account, which causes
a problem for those who need to monitor multiple accounts at once as there is no
easy way to aggregate and analyze data from all the different AWS accounts.

Thus, we provide our solution: ***AWS Trusted Advisor Rollup***.

## Brief Introduction:
Our implementation centers around using lambda functions to switch into other
accounts, collect AWS Trusted Advisor data, then store the data to S3, all on a
daily basis. We are using the [serverless framework](https://www.npmjs.com/package/serverless)
to manage our stack creation and automate the upload process.

These are the two major steps within our implementation. Click for implementation
details.

1. [Collect account details and distribute work](#fetch_accounts)
  - [fetch_accounts.py](fetch_accounts.py)
2. [Pull Trusted Advisor data and upload to AWS S3](#collect_data)
  - [run_checks.py](run_checks.py)


All [required variables](#required_variables) must be specified in [serverless.yml](serverless.yml), and the
[required permissions](#permissions) must be satisfied for the
accounts in order for ***AWS Trusted Advisor Rollup to work***.

## Usage
1). Install the serverless framework  
> npm i serverless

2). Install python requirements
> npm i serverless-python-requirements  
> sls plugin install -n serverless-python-requirements

3). Fill in [required variables](#required_variables) and check if [permissions](#permissions) have been satisfied.
***If the account information is not stored on a DynamoDB table, please change the
get_account_ids() function in [fetch_accounts.py](fetch_accounts.py)***

4). Setup AWS credentials.

5). Deploy stack with serverless deploy
> sls deploy  
> sls deploy --aws-profile [account]   

<a name="required_variables"></a>
## Required Variables:
All variables can be found in the **custom** section within serverless.yml.
* service:
    * Determines the name of the CloudFormation stack
    * *Ex. aws-trusted-advisor-rollup*
* region:
    * Specifies where all resources will be located
    * *Ex. us-east-1*
* 'AccountId':
    * The 'AccountId' of the starting account which can be found in the IAM console.
        * The 'starting account' is defined as where the resources such as lambda,
    S3, and SQS will be located.        
* queueName:
    * Name of the SQS queue
* bucketName:
    * Name of the S3 bucket to store AWS Trusted Advisor information.
* cronSchedule:
    * Cron Expression used to specify the running schedule.
        * [Cron Expression Introduction](https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html)
* dynamoName:
    * Name of the dynamoDB table that stores account information.
    * **Must have the 'AccountName' and 'AccountId' fields**
    * ***Optional***
* baseRole:
    * Base Role that should be propagated across all accounts. Just the name only, not the full ARN.
* executionRole:
    * Lambda execution role that will be running the lambda functions. Just the name only, not the full ARN.

## Permissions
***MAKE SURE ALL PERMISSIONS ARE SATISFIED***  

*Current Role*: Responsible for hosting all required AWS resources.   
*Base Role*: Propagated through all accounts to collect Trusted Advisor data  
*Execution Role*: Executes lambda functions.

*Starting Account*: Responsible for hosting all required AWS resources.   
*Target Accounts*: Accounts that will be providing AWS Trusted Advisor data.

* Roles
    * Current Role:
        * S3 (Create bucket for data)
        * CloudFormation (Serverless framework to upload entire stack)
        * IAM  (Create Execution Role for lambda functions)
        * Lambda (Host functions)
        * SQS (Queue to store and distribute messages)    
    * Base Role:
        * Support (Pull AWS Trusted Advisor data)
        * Trusted Relationship to Execution Role.
            * STS works like a handshake - the execution role must have the permissions to call
            the assume role function, and the base role (in the targetted account) it assumes into must trust the execution role.  
    * Execution Role:
        * S3 (Write to and read from S3 buckets)
        * STS (Switch to other accounts)
        * SQS (Send messages to queue)
        * CloudWatch (Write logs)
        * DynamoDB (Scan accounts table assuming you are using this)


## Detailed Steps
*The two python files below each serve as a lambda function.*  

Our implementation collects Trusted Advisor data by 'switching' into other
accounts. The 'switching' is done by calling the function assume_role(), which
essentially returns a session based on a role in the targeted account. This is
the reason there needs to be a base role propagated throughout all accounts, as
our implementation will be systematically switching into each role in each
targeted account.
<a name="fetch_accounts"></a>
### Fetch Accounts ([fetch_accounts.py](fetch_accounts.py))
*Triggered by a CloudWatch schedule specified by a Cron expression*  

Assume_role works by taking in an ARN. The ARN is structured as follows:
> arn:aws:iam::[account_id]:role/[base_role]  

Thus, to call assume_role(), we must know what the 'AccountId' is. Our implementation
provides a function that can retrieve the 'AccountId' and 'AccountName' if they
are stored in a DynamoDB table. If they aren't, please fill in the function and
and be sure to return the right values.

After retrieving all the 'AccountId's and 'AccountName', we send them to a SQS (simple
queue service) queue. Each 'message' within the queue will consist of one
'AccountName' and one 'AccountId'. The queue could then distribute the 'messages' to
different instances of the same account processing lambda function, and thus
parallelize the entire account processing step. This grants our function
scalability, speed, and it also resolves the time limit AWS imposes upon lambda
functions.

<a name="collect_data"></a>
### Collect AWS Account Details ([run_checks.py](run_checks.py))
*Triggered by aforementioned SQS*  

Lambda function will receive the 'AccountId' and 'AccountName' through SQS, and
start the AWS Trusted Advisor data collection process. With all the proper
permissions in place, this function will switch into another account by calling
assume_role(), pull the Trusted Advisor data, compile it to a CSV file, then
upload the file to the specific S3 bucket. The way we structed the S3 bucket is
to have folders with the date as their names (*ex. 2019-07-18*), and all the CSV
files will be named after the 'AccountName' received from SQS.

We have decided to store these values in the CSV files:  
    * Date
    * Account id
    * Status (Error, Warning, Ok, Not Available)
    * Check id
    * Check name (Currently, Trusted Advisor provides 109 checks in total)
    * Estimated monthlysavings
    * Account name
    * Category (Currently, Trusted Advisor is based on 5 categories)

# Thank you
### Contributors
* [Allen Chen](https://github.com/allenc3)
* [Bailey Tincher](https://github.com/baileytincher)
