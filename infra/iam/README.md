# GitHub deploy role IAM policy

`asx-risk-github-deploy-policy.json` is the least-privilege identity-based
policy for the `asx-risk-github-deploy` IAM role (assumed by GitHub Actions
via OIDC in `.github/workflows/deploy.yml`).

## Why the role needs this much

`sam deploy` in `deploy.yml` does not pass `--role-arn`, so CloudFormation
performs every resource action **as the calling identity**
(`asx-risk-github-deploy`) rather than through a separate CloudFormation
execution role. That means the role needs direct permissions for every
resource type `template.yaml` creates, not just `cloudformation:*`:

- CloudFormation stack/change-set operations on both
  `aws-sam-cli-managed-default` (SAM's own artifact stack) and
  `asx-risk-platform` (this project's stack).
- The SAM CLI-managed S3 artifact bucket (`aws-sam-cli-managed-default-samclisourcebucket-*`)
  and the project's `RawDataBucket` (`asx-risk-data-lake-<account>-<region>`).
- The seven named Lambda functions in `template.yaml`.
- The `asx-risk-daily-pipeline` Step Functions state machine.
- The `ScheduleV2` EventBridge Scheduler entry (schedule group `default`) and,
  on first use, the `AWSServiceRoleForScheduler` service-linked role.
- The SQS failure queue and SNS failure topic (CloudFormation-generated
  names, scoped with an `asx-risk-platform-*` prefix).
- The IAM roles CloudFormation generates for `PipelineFunctionRole` and the
  Step Functions/Scheduler execution roles (also `asx-risk-platform-*`
  prefixed under `CAPABILITY_IAM`), plus a conditioned `iam:PassRole` so
  those roles can be attached to Lambda, Step Functions, and Scheduler.

Resource ARNs are scoped exactly wherever `template.yaml` gives a resource a
static name (Lambda functions, the state machine, the raw-data bucket,
both CloudFormation stacks). Where CloudFormation auto-generates a resource
name (IAM roles, the SQS queue, the SNS topic, the SAM artifact bucket),
the policy uses the narrowest predictable prefix/pattern instead of `*`.

## Applying it

```bash
aws iam put-role-policy \
  --role-name asx-risk-github-deploy \
  --policy-name asx-risk-platform-deploy \
  --policy-document file://infra/iam/asx-risk-github-deploy-policy.json
```

Verify with:

```bash
aws iam list-role-policies --role-name asx-risk-github-deploy
aws iam get-role-policy --role-name asx-risk-github-deploy --policy-name asx-risk-platform-deploy
```

## Hardening follow-up

A cleaner long-term pattern is a dedicated `CloudFormationExecutionRole`
(trusted by `cloudformation.amazonaws.com`) holding the resource-creation
permissions above, with `asx-risk-github-deploy` reduced to just the
`ManageSamDeploymentStacks` statement plus a scoped `iam:PassRole` for that
one execution role, referenced via `sam deploy --role-arn`. This is not
implemented yet because it also requires a `deploy.yml` change; tracked as
a follow-up rather than bundled with this policy doc.
