# Troubleshooting Guide

This guide provides solutions to common issues you might encounter during development.

## `make dev` fails with "Port Already Allocated"

**Symptom:**
```
Error: Bind for 0.0.0.0:27017 failed: port is already allocated
```

**Cause:**
Another Docker container (likely from another project) is already using the port required by one of the services (e.g., 27017 for MongoDB, 6379 for Redis).

**Solution:**
1.  **Stop all other Docker containers:**
    ```bash
    docker stop $(docker ps -q)
    ```
2.  **Or, stop only the conflicting project's containers.**
3.  **Restart the services for this project:**
    ```bash
    make dev
    ```

## API container is `unhealthy` with `Authentication failed`

**Symptom:**
The API container is in an `unhealthy` state, and the logs show `pymongo.errors.OperationFailure: Authentication failed.`

**Cause:**
Stale Docker volumes from a previous setup with different database credentials.

**Solution:**
1.  **Stop and remove all containers and volumes (this will delete all data):**
    ```bash
    make clean-all
    ```
2.  **Run the setup process again:**
    ```bash
    make setup
    ```
3.  **Start the services:**
    ```bash
    make dev
    ```

## Code changes are not reflected in the container

**Symptom:**
You've made changes to the source code, but the application running in the Docker container is still showing the old behavior.

**Cause:**
The development environment uses hot-reloading, but sometimes you might need to force a rebuild of the container, especially if you've changed dependencies or Dockerfile configurations. A simple `docker compose restart` is not enough as it doesn't reload environment variables or rebuild the image.

**Solution:**
-   **To rebuild a specific service (e.g., the API):**
    ```bash
    make rebuild-api
    ```
-   **To rebuild all services:**
    ```bash
    make rebuild-all
    ```
These commands will build the container images without using the cache and then recreate the containers.

## Nginx `413 Content too large`

**Symptom:**
When uploading a large file, you get a `413 Content too large` error from Nginx.

**Cause:**
The default Nginx configuration has a limit for the client body size.

**Solution:**
1.  **Edit the Nginx configuration:** `infra/nginx/nginx.conf`
2.  **Increase the `client_max_body_size` value:**
    ```nginx
    client_max_body_size 50M; # Or a higher value
    ```
3.  **Rebuild the web container:**
    ```bash
    make rebuild-web
    ```
