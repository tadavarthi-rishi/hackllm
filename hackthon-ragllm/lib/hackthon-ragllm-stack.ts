import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as path from 'path';

export class LlmProjectStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 Bucket to store uploaded PDFs
    const bucket = new s3.Bucket(this, 'LLMPdfStorage', {
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Adjust based on your environment
    });

    // Lambda Role with permissions for Textract, S3, and other services
    const lambdaRole = new iam.Role(this, 'LambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    });

    lambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonTextractFullAccess'));
    lambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonS3FullAccess'));
    lambdaRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'));

    // Retrieve secrets from AWS Secrets Manager (replace with your secret name)
    const openAiSecret = secretsmanager.Secret.fromSecretNameV2(this, 'OpenAISecret', 'openai-api-key-secret');
    const pineconeSecret = secretsmanager.Secret.fromSecretNameV2(this, 'PineconeSecret', 'pinecone-api-key-secret');

    // Lambda function for POST (file upload and text extraction)
    const postLambda = new lambda.Function(this, 'LLMPostLambda', {
      runtime: lambda.Runtime.PYTHON_3_9, // Python runtime
      handler: 'file_processing.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda')), // No bundling options
      role: lambdaRole,
      timeout: cdk.Duration.seconds(60), // Set timeout to 60 seconds
      environment: {
        'BUCKET_NAME': bucket.bucketName,
        'OPENAI_SECRET_NAME': openAiSecret.secretName,
        'PINECONE_SECRET_NAME': pineconeSecret.secretName,
      },
    });

    // Allow S3 bucket to trigger Lambda on file upload
    bucket.addEventNotification(s3.EventType.OBJECT_CREATED, new s3n.LambdaDestination(postLambda));

    // Lambda function for GET (query based on filename and question)
    const getLambda = new lambda.Function(this, 'LLMGetLambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'query_lambda.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda')), // No bundling options
      role: lambdaRole,
      timeout: cdk.Duration.seconds(60), // Set timeout to 60 seconds
      environment: {
        'OPENAI_SECRET_NAME': openAiSecret.secretName,
        'PINECONE_SECRET_NAME': pineconeSecret.secretName,
      },
    });

    // Grant the Lambda functions permission to read the secrets from Secrets Manager
    openAiSecret.grantRead(postLambda);
    pineconeSecret.grantRead(postLambda);
    openAiSecret.grantRead(getLambda);
    pineconeSecret.grantRead(getLambda);

    // API Gateway for POST and GET methods
    const api = new apigateway.RestApi(this, 'LLMApi', {
      restApiName: 'LLM Service',
    });

    // POST method (upload PDF)
    const postApi = api.root.addResource('upload');
    postApi.addMethod('POST', new apigateway.LambdaIntegration(postLambda));

    // GET method (query with filename and question)
    const getApi = api.root.addResource('query');
    getApi.addMethod('GET', new apigateway.LambdaIntegration(getLambda));

    // Output the S3 bucket name and API Gateway URL
    new cdk.CfnOutput(this, 'UploadBucketName', { value: bucket.bucketName });
    new cdk.CfnOutput(this, 'ApiEndpoint', { value: api.url });
  }
}
