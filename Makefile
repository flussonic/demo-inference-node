build:
	docker build -t opencv .

run: build
	docker run -v `pwd`:/src -p 8020:8020 -e CONFIG_EXTERNAL=${CONFIG_EXTERNAL} --rm -it opencv
