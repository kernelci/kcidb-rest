#!/usr/bin/env python3
import json
import datetime
from kcidb_model import Build, Checkout, Test, Status, Kcidb, Version, Resource
from kernelci.config import merge_trees
import kernelci.api
import yaml
import re
import os
import logging
import sys
import requests
import argparse
from pydantic import AnyUrl


MISSED_TEST_CODES = (
    "Bug",
    "Configuration",
    "Infrastructure",
    "invalid_job_params",
    "Job",
    "job_generation_error",
    "ObjectNotPersisted",
    "RequestBodyTooLarge",
    "submit_error",
    "Unexisting permission codename.",
    "kbuild_internal_error",
)

ERRORED_TEST_CODES = (
    "Canceled",
    "LAVATimeout",
    "MultinodeTimeout",
    "Test",
)

# print debug messages
logging.basicConfig(level=logging.DEBUG)


class MaestroConverter:
    def __init__(self, pipeline_cfg_dir="config"):
        self.pipeline_cfg_dir = pipeline_cfg_dir
        self.builds = []
        self.checkouts = []
        self.tests = []
        self.pipeline_cfg = {}
        self.load_pipeline_cfg()
        self.log = logging.getLogger(__name__)
        self.origin = "maestro"
        self._node_cache = {}
        self.treeids = []
        self.api = None

    def _get_output_files(self, artifacts: dict, exclude_properties=None):
        output_files = []
        for name, url in artifacts.items():
            if exclude_properties and name in exclude_properties:
                continue
            # Replace "/" with "_" to match with the allowed pattern
            # for "name" property of "output_files" i.e. '^[^/]+$'
            name = name.replace("/", "_")
            # url is not str, it is AnyUrl object
            url_obj = AnyUrl(url)
            res = Resource(name=name, url=url_obj)
            output_files.append(res)
        return output_files

    def _parse_node_result(self, test_node):
        if test_node["result"] == "incomplete":
            error_code = test_node["data"].get("error_code")
            if error_code in ERRORED_TEST_CODES:
                return "ERROR"
            if error_code in MISSED_TEST_CODES:
                return "MISS"
            self.log.debug(f"Error code is not set for {test_node['id']}")
            return None
        return test_node["result"].upper()
    
    def _replace_restricted_chars(self, path, pattern, replace_char='_'):
        # Replace restricted characters with "_" to match the allowed pattern
        new_path = ""
        for char in path:
            if not re.match(pattern, char):
                new_path += replace_char
            else:
                new_path += char
        return new_path


    def _parse_node_path(self, path):
        """Parse and create KCIDB schema compatible node path
        Convert node path list to dot-separated string. Use unified
        test suite name to exclude build and runtime information
        from the test path.
        For example, test path ['checkout', 'kbuild-gcc-10-x86', 'baseline-x86']
        would be converted to "boot"
        """
        if isinstance(path, list):
            # nodes with path such as ['checkout', 'kbuild-gcc-10-x86', 'baseline-x86']
            parsed_path = path[2:]
            # Handle node with path ['checkout', 'kbuild-gcc-10-x86', 'sleep', 'sleep']
            if len(parsed_path) >= 2:
                    if parsed_path[0] == parsed_path[1]:
                        parsed_path = parsed_path[1:]
            new_path = []
            for sub_path in parsed_path:
                if sub_path in self.pipeline_cfg["jobs"]:
                    suite_name = self.pipeline_cfg["jobs"][sub_path].get("kcidb_test_suite")
                    if suite_name:
                        new_path.append(suite_name)
                    else:
                        self.log.error(
                            f"KCIDB test suite mapping not found for \
the test: {sub_path}"
                        )
                        return None
                else:
                    new_path.append(sub_path)
            # Handle path such as ['tast-ui-x86-intel', 'tast', 'os-release'] converted
            # to ['tast', 'tast', 'os-release']
            if len(new_path) >= 2:
                if new_path[0] == new_path[1]:
                    new_path = new_path[1:]
            path_str = ".".join(new_path)
            # Allowed pattern for test path is ^[.a-zA-Z0-9_-]*$'
            formatted_path_str = self._replace_restricted_chars(
                path_str, r"^[.a-zA-Z0-9_-]*$"
            )
            return formatted_path_str if formatted_path_str else None
        return None
    
    def _platform_compatible(self, platform):
        # get in platforms: named platform and get param from it
        pcfg = self.pipeline_cfg["platforms"].get(platform)
        if pcfg:
            return pcfg.get("compatible")
        return None
    
    def _is_checkout_child(self, json_data):
        return len(json_data["path"]) == 2 and json_data["path"][0] == "checkout"

   
    def _get_lab_base_url(self, lab_id):
        runtimes = self.pipeline_cfg["runtimes"]
        labdata = runtimes.get(lab_id)
        if labdata:
            return labdata.get("url")
        return None
    
    def _cached_node_get(self, node_id):
        if node_id not in self._node_cache:
            self._node_cache[node_id] = self.api.node.get(node_id)
        else:
            self.log.debug(f"Using cached node {node_id}")
        return self._node_cache[node_id]
    
    def _get_parent_job(self, node):
        # walk up by 'parent' field
        # until we reach node with kind 'job'
        # return job_id
        while node["kind"] != "job":
            node = self._cached_node_get(node["parent"])
            if not node["parent"]:
                return None
        return node
    
    def _get_parent_kbuild(self, node):
        # walk up by 'parent' field
        # until we reach node with kind 'kbuild'
        # return job_id
        while node["kind"] != "kbuild":
            node = self._cached_node_get(node["parent"])
            if not node["parent"]:
                return None
        return node

    def load_pipeline_cfg(self):
        # iterate over all yaml files in the pipeline_cfg_dir
        for file in os.listdir(self.pipeline_cfg_dir):
            if file.endswith(".yaml"):
                with open(os.path.join(self.pipeline_cfg_dir, file), "r") as f:
                    self.pipeline_cfg = merge_trees(
                        self.pipeline_cfg, yaml.safe_load(f)
                    )

    def load_maestro_node(self, submission, json_data):
        name = json_data["name"]
        # if name contains "dtbscheck" force-set to kbuild
        # TODO: Fix it in Maestro
        if "dtbscheck" in name:
            # TODO: We need to fix hierarchy of nodes in Maestro
            self.log.debug(f"Ignoring nodes with dtbscheck in name: {name}")
            return submission
        if json_data["kind"] == "kbuild":
            build_node = self.process_build(json_data)
            if build_node:
                submission.builds.append(build_node)
            else:
                self.log.error(f"Build {json_data['id']} is not valid")
        elif json_data["kind"] == "checkout":
            checkout_node = self.process_checkout(json_data)
            if checkout_node:
                submission.checkouts.append(checkout_node)
            else:
                self.log.error(f"Checkout {json_data['id']} is not valid")
        elif json_data["kind"] == "test" or json_data["kind"] == "job":
            test_node = self.process_test(json_data)
            if test_node:
                submission.tests.append(test_node)
            else:
                self.log.error(f"Test {json_data['id']} is not valid")
        else:
            raise ValueError(f"Unknown node kind: {json_data['kind']}")
        
        return submission

    def get_kbuild_architecture(self, jobname):
        jobs = self.pipeline_cfg["jobs"]
        job = jobs.get(jobname)
        if job:
            params = job.get("params")
            if params:
                return params.get("arch")
        return None

    def get_kbuild_compiler(self, jobname):
        jobs = self.pipeline_cfg["jobs"]
        job = jobs.get(jobname)
        if job:
            params = job.get("params")
            return params.get("compiler")
        return None

    def process_checkout(self, json_data):
        self.log.debug(f"Processing checkout {json_data['id']}")
        result = json_data.get("result")

        # Don't send "timed-out" checkout node to KCIDB
        if (
            result == "incomplete"
            and json_data["data"].get("error_code") == "node_timeout"
        ):
            self.log.debug(f"Skipping checkout {json_data['id']} due to timeout")
            return None

        result_map = {
            "pass": True,
            "fail": False,
            "incomplete": False,
        }
        valid = result_map[result] if result else None
        krev = json_data.get("data").get("kernel_revision")

        checkout_data = Checkout(
            id=f"{self.origin}:{json_data['id']}",
            origin=self.origin,
            tree_name=krev.get("tree"),
            comment=krev.get("describe"),
            git_repository_url=krev.get("url"),
            git_commit_hash=krev.get("commit"),
            git_commit_name=krev.get("describe"),
            git_repository_branch=krev.get("branch"),
            git_commit_tags=krev.get("commit_tags"),
            git_commit_message=krev.get("commit_message"),
            git_repository_branch_tip=krev.get("tip_of_branch"),
            start_time=datetime.datetime.fromisoformat(json_data["created"]).replace(tzinfo=datetime.timezone.utc),
            patchset_hash="",
            misc={"submitted_by": "kernelci-pipeline"},
            valid=valid,
        )
        return checkout_data

    def process_build(self, json_data):
        self.log.debug(f"Processing build {json_data['id']}")
        # Extracting data from Maestro JSON and mapping to Build object
        job_name = json_data.get("name")
        build_data = Build(
            checkout_id=f"{self.origin}:{json_data['parent']}",
            id=f"{self.origin}:{json_data['id']}",
            origin=self.origin,
            comment=json_data.get("data").get("kernel_revision").get("describe"),
            start_time=datetime.datetime.fromisoformat(json_data["created"]).replace(tzinfo=datetime.timezone.utc),
            architecture=self.get_kbuild_architecture(job_name),
            compiler=self.get_kbuild_compiler(job_name),
            command=None,  # No command provided in example
            config_name=json_data.get("data").get("config_full"),
            status=self._parse_node_result(json_data),
            duration=None,
            log_url=None,
            log_excerpt=None,
            input_files=None,
            output_files=None,
            misc={
                "job_id": json_data["data"].get("job_id"),
                "runtime": json_data["data"].get("runtime"),
                "platform": json_data["data"].get("platform"),
                "job_context": json_data["data"].get("job_context"),
                "kernel_revision": json_data["data"].get("kernel_revision"),
                "kernel_type": json_data["data"].get("kernel_type"),
                "error_code": json_data["data"].get("error_code"),
                "error_msg": json_data["data"].get("error_msg"),
                "lab": json_data["data"].get("runtime"),
                "maestro_viewer": f"https://api.kernelci.org/viewer?node_id={json_data['id']}",
            },
        )
        artifacts = json_data.get("artifacts")
        if artifacts:
            build_data.output_files = self._get_output_files(
                artifacts=artifacts,
                exclude_properties=('build_log', '_config')
            )
            cfg_url = artifacts.get('_config')
            if cfg_url:
                build_data.config_url = AnyUrl(cfg_url)
            else:
                self.log.error(f"Build {json_data['id']} missing config")
                return None
            log_url = artifacts.get('build_log')
            if log_url:
                build_data.log_url = AnyUrl(log_url)
            else:
                self.log.error(f"Build {json_data['id']} missing log")
                return None

        return build_data

    def process_test(self, json_data):
        if self._is_checkout_child(json_data):
            return None
        path = json_data['path']
        if 'setup' in path and 'os-release' not in path:
            # do not send setup tests except `os-release`
            print(f"Skipping setup test {json_data['id']} as its setup related")
            return None
        parent_job = self._get_parent_job(json_data)
        if not parent_job:
            # TODO: This is maybe kselftest build tests and etc
            return None
        name = json_data["name"]
        # TODO: ignore kunits now as they dont have parent build
        # their name start with kunit
        if name.startswith("kunit"):
            self.log.debug(f"Skipping kunit test {json_data['id']}")
            return None

        platform = json_data["data"].get("platform")
        platform_compatible = self._platform_compatible(platform)
        if not platform_compatible:
            self.log.debug(f"Test {json_data['id']} missing platform {platform} compat field")

        runtime = json_data["data"].get("runtime")
        is_checkout_child = self._is_checkout_child(json_data)
        kbuild_parent = self._get_parent_kbuild(json_data)
        if not kbuild_parent:
            self.log.debug(f"Test {json_data['id']} missing kbuild parent")
            return None

        test_data = Test(
            build_id=f"{self.origin}:{kbuild_parent['id']}",
            id=f"{self.origin}:{json_data['id']}",
            origin=self.origin,
            comment=f"{json_data['name']} on {platform} in {runtime}",
            start_time=datetime.datetime.fromisoformat(json_data["created"]).replace(tzinfo=datetime.timezone.utc),
            environment={
                "comment": f"Runtime: {runtime}",
                "compatible": platform_compatible,
                "misc": {
                    "platform": platform,
                    "measurement": None,
                }
            },
            path=self._parse_node_path(json_data['path']),
            status=self._parse_node_result(json_data),
            misc={
                "runtime": runtime,
                "maestro_viewer": f"https://api.kernelci.org/viewer?node_id={json_data['id']}",
            }
        )
        metadata = parent_job.get("data")
        if metadata:
            lab_id = metadata.get("runtime")
            lab_base_url = self._get_lab_base_url(lab_id)
            job_id = metadata.get("job_id")
            # TODO: Why we assume it's LAVA?
            if lab_base_url:
                test_data.misc["job_url"] = f"{lab_base_url}scheduler/job/{job_id}"
            test_data.environment.misc["job_id"] = job_id
            test_data.environment.misc["job_context"] = metadata.get("job_context")
            #test_data['environment']['misc']['job_id'] = metadata.get("job_id")
            #test_data['environment']['misc']['job_context'] = metadata.get("job_context")
        
        artifacts = json_data.get("artifacts")
        if artifacts:
            test_data.output_files = self._get_output_files(
                artifacts=artifacts,
                exclude_properties=('lava_log', 'test_log')
            )
            if artifacts.get('lava_log'):
                url_obj = AnyUrl(artifacts.get('lava_log'))
                test_data.log_url = url_obj
            else:
                artifact_url = artifacts.get('test_log')
                if not artifact_url:
                    self.log.error(f"Test {json_data['id']} missing log")
                    return None
                url_obj = AnyUrl(artifact_url)
                test_data.log_url = url_obj

            #log_url = test_data.log_url
            #if log_url:
            #    test_data.log_excerpt = self._get_log_excerpt(
            #        log_url)

        # TODO: We need to retrieve them from parent job
        test_data.misc['error_code'] = parent_job.get("data").get("error_code")
        test_data.misc['error_msg'] = parent_job.get("data").get("error_msg")
       
        return test_data


# Outputting JSON compatible with kcidb_model
# output_json = build_data.json(exclude_none=True, by_alias=True, indent=2)

# Save the converted JSON
# with open('kcidb_build_output.json', 'w') as outfile:
# outfile.write(output_json)

# print("Converted JSON saved as 'kcidb_build_output.json'")

def submit_kcidb_node(json_str):
    hdr = {"Authorization": "your_api_key_here", "Content-Type": "application/json"}
    encoded_json = json_str.encode('utf-8')
    requests.post("http://localhost:7000/submit", headers=hdr, data=encoded_json)

def generate_submission(converter, trees_num=50):
    submission = Kcidb(
        version=Version(
            major=5,
            minor=1,
        ),
        checkouts=[],
        builds=[],
        tests=[],
        issues=[],
        incidents=[],
    )

    cnt = 0
    while converter.treeids:
        # get treeid from the list
        treeid = converter.treeids.pop(0)
        if not treeid:
            break
        filter = {
            'treeid': treeid,
            'state': 'done',
        }
        cnt += 1
        nodes = converter.api.node.findfast(filter)
        # add to cache hack TODO: fix?
        for node in nodes:
            converter._node_cache[node['id']] = node

        for node in nodes:
            submission = converter.load_maestro_node(submission, node)
        

        if cnt > trees_num:
            break

    if cnt == 0:
        logging.error("No nodes found")
        return None

    # validate integrity, all builds should have valid reference to checkout
    for build in submission.builds:
        checkout_id = build.checkout_id
        # check if checkout_id is in submission.checkouts
        if checkout_id not in [checkout.id for checkout in submission.checkouts]:
            logging.error(f"Build {build.id} has invalid checkout reference {checkout_id}")
            continue
    # validate tests, similar to builds
    for test in submission.tests:
        build_id = test.build_id
        # check if build_id is in submission.builds
        if build_id not in [build.id for build in submission.builds]:
            logging.error(f"Test {test.id} has invalid build reference {build_id}")
            continue  


    json_str = submission.model_dump_json(exclude_none=True, by_alias=True, indent=2)
    return json_str

# API DATA IS:
#    timeout: 60
#    url: https://kernelci-api.westus3.cloudapp.azure.com
#    version: latest


def get_treeids():
    converter = MaestroConverter()
    api_data = """
    timeout: 60
    url: https://kernelci-api.westus3.cloudapp.azure.com
    version: latest
    """
    api_config = kernelci.config.api.API.load_from_yaml(
            yaml.safe_load(api_data), name='api'
        )
    converter.api = kernelci.api.get_api(api_config)
    # get the last 24 hours
    isodate_now = datetime.datetime.now().isoformat()
    isodate_creation = (
        datetime.datetime.now() - datetime.timedelta(days=7)
    ).isoformat()
    nodes = converter.api.node.findfast({
        'state': 'done',
        'kind': 'checkout',
        'created__gt': isodate_creation,
    })
    for node in nodes:
        if 'treeid' in node:
            converter.treeids.append(node['treeid'])
    return converter

def main():
    parser = argparse.ArgumentParser(description="Submit Maestro data to KCIDB")
    parser.add_argument(
        "-c", "--config", type=str, help="Path to Maestro-pipeline config directory"
    )
    parser.add_argument(
        "-s", "--submission", type=str, help="Path to Maestro submission file"
    )

    args = parser.parse_args()
    json_str = None
    if args.config:
        converter.pipeline_cfg_dir = args.config

    if args.submission:
        with open(args.submission, "r") as f:
            json_str = f.read()
            submit_kcidb_node(json_str)
    else:
        converter = get_treeids()
        while True:
            json_str = generate_submission(converter, 5)
            if json_str is None:
                print("No data to submit")
                break
            else:
                print(f"Generated json, for several trees")
            # save to submission.json
            with open("submission.json", "w") as f:
                f.write(json_str)
            print(f"Size of json: {len(json_str)}")                
            submit_kcidb_node(json_str)

if __name__ == "__main__":
    main()
