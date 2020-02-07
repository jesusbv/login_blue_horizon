import logging
import os
import glob
import subprocess
import ast
from collections import namedtuple
from textwrap import dedent

log = logging.getLogger('blue-horizon-login')

def command_run(command, custom_env=None, raise_on_error=True):
    command_type = namedtuple(
        'command', ['output', 'error', 'returncode']
    )
    environment = os.environ
    if custom_env:
        environment = custom_env

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment
        )
    except Exception as issue:
        print(
            '{0}: {1}: {2}'.format(command[0], type(issue).__name__, issue)
        )
        raise Exception(
            '{0}: {1}: {2}'.format(command[0], type(issue).__name__, issue)
        )
    output, error = process.communicate()
    if process.returncode != 0 and not error:
        error = bytes(b'(no output on stderr)')
    if process.returncode != 0 and not output:
        output = bytes(b'(no output on stdout)')
    if process.returncode != 0 and raise_on_error:
        print(
            'EXEC: Failed with stderr: {0}, stdout: {1}'.format(
                error.decode(), output.decode()
            )
        )
        raise Exception(
            '{0}: stderr: {1}, stdout: {2}'.format(
                command[0], error.decode(), output.decode()
            )
        )
    return command_type(
        output=output.decode(),
        error=error.decode(),
        returncode=process.returncode
    )

def get_subscription_id(curl_output):
    return curl_output['compute']['subscriptionId']

def get_public_ip(curl_output):
    return curl_output['network']['interface'][0]['ipv4']['ipAddress'][0]["publicIpAddress"]

def get_instance_name(curl_output):
    return curl_output['compute']['name']

def get_instance_metadata():
    curl_command = command_run(
        ['curl', '-H', 'Metadata:true', 'http://169.254.169.254/metadata/instance?api-version=2019-06-01']
    )
    return ast.literal_eval(curl_command.output)

def create_htpasswd(instance_metadata):
    username = get_instance_name(instance_metadata)
    subscription_id = get_subscription_id(instance_metadata)
    htpasswd_path = os.sep.join(
        ['/etc', 'nginx', '.htpasswd']
    )
    # create user:passwd in .htpasswd file
    passwd_cmd = command_run(
        ['openssl', 'passwd', '-apr1', subscription_id]
    )
    with open(htpasswd_path, 'w') as htpasswd_file:
        htpasswd_file.write(
            '{0}:{1}'.format(username, passwd_cmd.output)
        )
    log.info(
        '.htpasswd created in {}'.format(htpasswd_path)
    )
    return htpasswd_path

def create_nginx_rule(instance_metadata, htpasswd_path):
    subscription_id = get_subscription_id(instance_metadata)
    public_ip = get_public_ip(instance_metadata)

    home_path = glob.glob(
        os.sep.join(
            ['/home', '*']
        )
    )[0]
    root_path = os.sep.join(
        [home_path, 'www']
    )  # wherever the rails app is

    nginx_rule = dedent('''
    server {{
        listen 80;
	listen [::]:80;
        server_name test.com www.test.com;
        root {0};
        index index.html;
	allow 127.0.0.1;
	allow {1};
	auth_basic	'Test';
	auth_basic_user_file {2};
    }}
''')
    nginx_rule = nginx_rule.format(root_path, public_ip, htpasswd_path)
    nginx_login_rule_path = '/etc/nginx/conf.d/blue_horizon_login.conf'
    with open(nginx_login_rule_path, 'w+') as nginx_login_rule_file:
        nginx_login_rule_file.write(nginx_rule)
        log.info(
            'Nginx rule created in {}'.format(nginx_login_rule_path)
        )

# PROCESS
instance_metadata = get_instance_metadata()
if type(instance_metadata) is dict and instance_metadata:
    htpasswd_path = create_htpasswd(instance_metadata)
    create_nginx_rule(instance_metadata, htpasswd_path)
    log.info('Done.')
else:
    log.warning('No instance metadata. Process finished.')
