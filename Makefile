build:
	docker build -t opencv .

run:
	docker run -v `pwd`:/src --rm -it opencv

