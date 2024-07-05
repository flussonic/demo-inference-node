build:
	docker build -t opencv .

run:
	docker run -v `pwd`:/src -p 8000:8000 --rm -it opencv

