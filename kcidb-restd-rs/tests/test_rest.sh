#!/bin/bash
# This scripts tests kcidb-rest API

rm -f test.out
echo "Testing / endpoint"
curl -v http://localhost:8080/ > test.out 2>&1
grep -q "404 Not Found" test.out
if [ $? -ne 0 ]; then
    echo "Index test: [31mError: 404 Not Found[0m"
    exit 1
else
    echo "Index test: [32mOK[0m"
fi

echo "Testing /status endpoint with no auth"
curl -v http://localhost:8080/status > test.out 2>&1
grep -q "401 Unauthorized" test.out
if [ $? -ne 0 ]; then
    echo "Status test: [31mError: 401 Unauthorized[0m"
    exit 1
else
    echo "Status test: [32mOK[0m"
fi


echo "Testing /status endpoint with auth"
SECRET="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJvcmlnaW4iOiJ0ZXN0IiwiZ2VuZGF0ZSI6IjIwMjUtMDUtMjNUMDA6Mjg6MzFaIiwiZXhwIjoxOTA1NjI5MzExfQ.zLGkw5sBZf6jRtUisjCvP-X9_6ttSG1IFzioVIkltAY"
curl -v http://localhost:8080/status -H "Authorization: Bearer $SECRET" > test.out 2>&1
grep -q "400 Bad Request" test.out
if [ $? -ne 0 ]; then
    echo "Status test: [31mError: 400 Bad Request[0m"
    exit 1
else
    echo "Status test: [32mOK[0m"
fi

# generate random text data to submit.json
dd if=/dev/urandom bs=1 count=1000 2>/dev/null | base64 > submit.json

echo "Testing /submit endpoint with no auth"
curl -v -X POST http://localhost:8080/submit -d @submit.json > test.out 2>&1
grep -q "401 Unauthorized" test.out
if [ $? -ne 0 ]; then
    echo "Submit test: [31mError: 401 Unauthorized[0m"
    exit 1
else
    echo "Submit test: [32mOK[0m"
fi

echo "Testing /submit endpoint with auth but invalid file"
curl -v -X POST http://localhost:8080/submit -d @submit.json -H "Authorization: Bearer $SECRET" > test.out 2>&1
grep -q "400 Bad Request" test.out
if [ $? -ne 0 ]; then
    echo "Submit test: [31mError: 400 Bad Request[0m"
    exit 1
else
    echo "Submit test: [32mOK[0m"
fi

# generate simple json for /submit
cat <<EOF > submit.json
{
    "data": "test"
}
EOF

echo "Testing /submit endpoint with auth"
curl -v -X POST http://localhost:8080/submit -d @submit.json -H "Authorization: Bearer $SECRET" > test.out 2>&1
grep -q "200 OK" test.out
if [ $? -ne 0 ]; then
    echo "Submit test: [31mError: 200 OK[0m"
    exit 1
else
    echo "Submit test: [32mOK[0m"
fi

echo "All tests passed"
echo "Cleaning up"

# cleanup
rm -f test.out
rm -f submit.json
echo "Thank you for flying with us!"
echo "Have a nice day!"
