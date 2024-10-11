import aws_cdk
import platform
from pathlib import Path
from constructs import Construct
from aws_cdk import (aws_dynamodb as ddb,
                     aws_ecr_assets,
                     aws_iam as iam,
                     aws_lambda as lambda_,
                     aws_logs as logs)


class Reservations(Construct):
    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 reservations_lambda_dir: Path = Path('lambda') / 'reservations',
                 lambda_platform: aws_ecr_assets.Platform | None = None,
                 lambda_architecture: lambda_.Architecture | None = None):
        """
        Construct for the Telegram API, fronted by an API gateway

        Parameters
        ----------
        scope : Construct scope (typically `self` from the caller)
        construct_id : Unique CDK ID for this construct
        reservations_lambda_dir : Path to the directory containing the source code for the
                                         Lambda that will set the webhook URL to the new API Gateway.
        lambda_platform : Platform to use for the lambdas. If not provided, use the platform of the current computer.
        lambda_architecture : Architecture for the lambda to run in. If not provided, use the platform of the
                              current computer. Must be coherent with `lambda_platform`.
        """
        super().__init__(scope, construct_id)

        # Default to current platform, useful since we'll compile the docker images
        if lambda_architecture is None or lambda_architecture is None:
            match platform.machine():
                case 'arm64':
                    lambda_platform = aws_ecr_assets.Platform.LINUX_ARM64
                    lambda_architecture = lambda_.Architecture.ARM_64
                case _:
                    lambda_platform = aws_ecr_assets.Platform.LINUX_AMD64
                    lambda_architecture = lambda_.Architecture.X86_64

        # Create the DynamoDB table for the Spa reservations
        self.reservations_table = ddb.TableV2(scope=self,
                                              id='Reservations',
                                              table_name='spa_reservations',
                                              partition_key=ddb.Attribute(name='date', type=ddb.AttributeType.STRING))
        base_lambda_policy = iam.ManagedPolicy.from_aws_managed_policy_name(
            managed_policy_name='service-role/AWSLambdaBasicExecutionRole')
        spa_lambda_role = iam.Role(scope=self,
                                   id='SpaReservationsLambdaRole',
                                   assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
                                   managed_policies=[base_lambda_policy])
        # Telegram API-related resources
        image = lambda_.DockerImageCode.from_image_asset(reservations_lambda_dir.as_posix(),
                                                         platform=lambda_platform)
        self.spa_lambda = lambda_.DockerImageFunction(scope=self,
                                                      id='SPAReservationsAPI',
                                                      code=image,
                                                      architecture=lambda_architecture,
                                                      environment={'DDB_TABLE_NAME':
                                                                       self.reservations_table.table_name},
                                                      timeout=aws_cdk.Duration.seconds(30),
                                                      role=spa_lambda_role,
                                                      log_retention=logs.RetentionDays.THREE_DAYS)
        self.reservations_table.grant_read_write_data(spa_lambda_role)
        self.spa_lambda.grant_invoke(iam.ServicePrincipal('apigateway.amazonaws.com'))
