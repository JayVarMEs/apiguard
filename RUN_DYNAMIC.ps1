$ErrorActionPreference = "Stop"
Invoke-RestMethod http://localhost:5000/createdb | Out-Null
$body = '{"username":"name1","password":"pass1"}'
$t = (Invoke-RestMethod -Method Post -Uri http://localhost:5000/users/v1/login -ContentType "application/json" -Body $body).auth_token
docker run --rm -v "${PWD}\demo\specs:/specs" schemathesis/schemathesis:stable run /specs/vampi_openapi3.yaml --url http://host.docker.internal:5000 --checks all --max-examples 50 -H "Authorization: Bearer $t" 2>&1 | Out-File -Encoding utf8 results\schemathesis_vampi_auth.txt
Write-Host "DONE"
