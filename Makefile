#!/usr/bin/make

mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
project_dir := $(dir $(realpath $(mkfile_path)))

author ?= "Canonical IS team"
revision ?= $(shell git -C $(project_dir) rev-parse HEAD)
date_created ?= $(shell date +'%Y%m%d%H%M')


build-image:
	docker build \
	  --build-arg DATE_CREATED="$(date_created)" \
	  --build-arg AUTHOR=$(author) \
	  --build-arg REVISION="$(revision)" \
	  -t jenkins-slave-operator:$(revision) $(project_dir)
