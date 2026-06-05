#!/bin/zsh

# Color tokens for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}====================================================${NC}"
echo -e "${YELLOW} Starting containerized test suite for Poster Portal ${NC}"
echo -e "${YELLOW}====================================================${NC}"

# 1. Build test image
echo -e "Building Docker test image..."
docker build -t posted-test -f Dockerfile .

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker build failed! Exiting.${NC}"
    exit 1
fi

# 2. Run tests in container
echo -e "\nRunning Pytest inside container..."
docker run --rm -e PYTHONPATH=/app -t posted-test pytest -v

TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✔ All tests passed successfully inside the container!${NC}"
else
    echo -e "\n${RED}✘ Some tests failed. Please review the output above.${NC}"
fi

exit $TEST_EXIT_CODE
