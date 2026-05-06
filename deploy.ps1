$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

$ProjectId = "eco-carver-356809"
$Region = "asia-east1"
$Repo = "han-cron"
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repo/han-jobs:latest"
$ServiceAccount = "han-cloud-run-jobs@$ProjectId.iam.gserviceaccount.com"

$gcloud = "C:\Users\bo.huang\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

& $gcloud config set project $ProjectId

& $gcloud services enable `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  run.googleapis.com `
  cloudscheduler.googleapis.com `
  secretmanager.googleapis.com `
  iam.googleapis.com `
  --project $ProjectId

$repoExists = & $gcloud artifacts repositories list --location $Region --project $ProjectId --filter "name:$Repo" --format "value(name)"
if (-not $repoExists) {
  & $gcloud artifacts repositories create $Repo `
    --repository-format docker `
    --location $Region `
    --description "HAN scheduled data jobs" `
    --project $ProjectId
}

$saExists = & $gcloud iam service-accounts list --project $ProjectId --filter "email:$ServiceAccount" --format "value(email)"
if (-not $saExists) {
  & $gcloud iam service-accounts create han-cloud-run-jobs `
    --display-name "HAN Cloud Run scheduled jobs" `
    --project $ProjectId
}

$roles = @(
  "roles/bigquery.dataEditor",
  "roles/bigquery.jobUser",
  "roles/logging.logWriter",
  "roles/run.developer",
  "roles/secretmanager.secretAccessor"
)
foreach ($role in $roles) {
  & $gcloud projects add-iam-policy-binding $ProjectId `
    --member "serviceAccount:$ServiceAccount" `
    --role $role `
    --condition=None `
    --quiet
}

function Ensure-SecretFile($Name, $File) {
  $secretExists = & $gcloud secrets list --project $ProjectId --filter "name:$Name" --format "value(name)"
  if (-not $secretExists) {
    & $gcloud secrets create $Name --replication-policy automatic --project $ProjectId
  }
  & $gcloud secrets versions add $Name --data-file $File --project $ProjectId
}

Ensure-SecretFile "han-googleads-token-py" ".\GoogleAds_api_token_Han.py"
Ensure-SecretFile "han-dable-token-py" ".\Dable_Parm_token.py"
Ensure-SecretFile "han-meta-token-py" ".\meta_token.py"
Ensure-SecretFile "han-bq-service-account-main-json" ".\eco-carver-356809-38c8914cd90f.json"
Ensure-SecretFile "han-bq-service-account-sheets-json" ".\eco-carver-356809-a5ccbfde00b9.json"

& $gcloud builds submit --tag $Image --project $ProjectId .

$jobs = @(
  @{Name="han-facebook-api-daily-cmb"; Script="facebook_api_daily_cmb.py"; Schedule="0 6 * * *"},
  @{Name="han-facebook-api-image"; Script="facebook_api_image.py"; Schedule="0 6 * * *"},
  @{Name="han-line-api-daily-cmb"; Script="line_api_daily_cmb.py"; Schedule="0 6 * * *"},
  @{Name="han-googleads-api-daily-0730"; Script="GoogleAds_API_daily.py"; Schedule="30 7 * * *"},
  @{Name="han-googleads-pmax-0830"; Script="GoogleAds_Pmax.py"; Schedule="30 8 * * *"},
  @{Name="han-dable-api-daily"; Script="Dable_API_daily.py"; Schedule="50 8 * * *"},
  @{Name="han-popin-api-daily-1100"; Script="popin_api_daily_cmb.py"; Schedule="0 11 * * *"},
  @{Name="han-googleads-pmax-1305"; Script="GoogleAds_Pmax.py"; Schedule="5 13 * * *"},
  @{Name="han-popin-api-daily-1400"; Script="popin_api_daily_cmb.py"; Schedule="0 14 * * *"},
  @{Name="han-googleads-api-daily-1740"; Script="GoogleAds_API_daily.py"; Schedule="40 17 * * *"},
  @{Name="han-googleads-pmax-1750"; Script="GoogleAds_Pmax.py"; Schedule="50 17 * * *"}
)

foreach ($job in $jobs) {
  $jobExists = & $gcloud run jobs list --region $Region --project $ProjectId --filter "metadata.name=$($job.Name)" --format "value(metadata.name)"
  $verb = if ($jobExists) { "update" } else { "create" }
  & $gcloud run jobs $verb $job.Name `
    --image $Image `
    --region $Region `
    --service-account $ServiceAccount `
    --set-env-vars "SCRIPT=$($job.Script)" `
    --set-secrets "GOOGLEADS_TOKEN_PY=han-googleads-token-py:latest,DABLE_TOKEN_PY=han-dable-token-py:latest,META_TOKEN_PY=han-meta-token-py:latest,BQ_MAIN_JSON=han-bq-service-account-main-json:latest,BQ_SHEETS_JSON=han-bq-service-account-sheets-json:latest" `
    --task-timeout 3600 `
    --max-retries 1 `
    --memory 2Gi `
    --cpu 1 `
    --project $ProjectId

  $schedulerName = "$($job.Name)-schedule"
  $schedulerExists = & $gcloud scheduler jobs list --location $Region --project $ProjectId --filter "name:$schedulerName" --format "value(name)"
  $schedulerVerb = if ($schedulerExists) { "update" } else { "create" }
  & $gcloud scheduler jobs $schedulerVerb http $schedulerName `
    --location $Region `
    --schedule $job.Schedule `
    --time-zone "Asia/Taipei" `
    --uri "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$($job.Name):run" `
    --http-method POST `
    --oauth-service-account-email $ServiceAccount `
    --project $ProjectId
}
