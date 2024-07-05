# Sample analytics node




## Structure

It has following classes that are mandatory for inference node:

1. `Manager` - fetches configuration from Central and reconfigures streams on fly
2. `Capture` - fetches RTSP stream from Flussonic streaming server and provides precise UTC timestamps
3. `EpisodesServer` - implements long-polling episodes endpoint required for fetching analytics events to Central
4. main.py is a launcher that can be customized by you.

## Customization

If has 2 dependency injection classes: `MyManager` and `QrDetector`


`MyManager` is an override of `Manager` that spawns workers. 
Function `launch` can take a look at `spec` and select which class to launch.

You can take a look at configuration of the stream and decide which `Capture` subclass to launch

We offer you `QrDetector` that will use opencv to find qr codes in video stream


## Running


1. `make build` to build docker
2. create file `streams` with following content to simulate central: `{"streams":[{"name":"cam2","url":"rtsp://your-flussonic/qr"}]}`
3. run `python3 -m http.server 9000` to work as a config_external server
4. now launch inference node: `make CONFIG_EXTERNAL=http://host.docker.internal:9000/ run`
5. Check that it has started:

```
$ make CONFIG_EXTERNAL=http://host.docker.internal:9000/ run
docker run -v `pwd`:/src -p 8020:8020 -e CONFIG_EXTERNAL=http://host.docker.internal:9000/ --rm -it opencv
Launch new <manager.Stream object at 0xffff921504a0>
First frame arrived on 2024-07-05 18:30:46.733678+00:00
```

This is ok. Now it will look for QR codes.

6. Run in another window polling episode fetcher:

```
$ curl -sS 'http://localhost:8020/episodes?poll_timeout=30&updated_at_gt=0' | jq
{
  "episodes": [
    {
      "episode_id": 1720204525414799,
      "media": "cam2",
      "opened_at": 1720204525414,
      "updated_at": 1720204525414,
      "payload": "tel:8007867411",
      "episode_type": "generic"
    }
  ]
}
```

Now take the last `updated_at` from the response and restart poll:

```
$ curl -sS 'http://localhost:8020/episodes?poll_timeout=30&updated_at_gt=1720204525414' | jq
{
  "episodes": [
    {
      "episode_id": 1720204531020733,
      "media": "cam2",
      "opened_at": 1720204531020,
      "updated_at": 1720204531020,
      "payload": "http://bannersonaroll.com",
      "episode_type": "generic"
    },
    {
      "episode_id": 1720204559728666,
      "media": "cam2",
      "opened_at": 1720204559728,
      "updated_at": 1720204559728,
      "payload": "http://blog.webometrics.org.uk",
      "episode_type": "generic"
    }
  ]
}
```


Mention that episode with payload `tel:800...` haven't arrived. This is how long-poll server works.

You do not need to run this curl by yourself, it is just a demonstration of how does Central fetches episodes from your node.

