# aws

The home-manager module that renders `~/.aws/config` from a set of profiles. It writes no keys to disk and never writes `~/.aws/credentials`: each profile names a `credential_process`, which the AWS CLI and SDKs run when they need keys. A flake takes it as `dnix.homeManagerModules.aws` and a host sets `dnix.aws.enable = true`.

## Files

```
default.nix         the options and the `programs.awscli` settings built from them
credentials-op.sh   aws-credentials-op, the credential_process behind a profile's `op`
test.nix            the check: the rendered sections, the assertion, the helper against a fake op
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.aws.enable` | `false` | Turns the module on and installs the AWS CLI through `programs.awscli`. |
| `dnix.aws.op.package` | `pkgs._1password-cli` | The `op` the helper calls. Unfree in nixpkgs. |
| `dnix.aws.profiles.<name>` | none | One `~/.aws/config` section: `[default]` for `default`, `[profile <name>]` otherwise. |

A profile:

| Field | Default | Meaning |
|---|---|---|
| `region` | required | the profile's region |
| `output` | `json` | the CLI's output format |
| `op` | `null` | read the keys from a 1Password item at each use: `vault`, `item` (name or id), and `fields.accessKeyId` / `fields.secretAccessKey`, the item's field labels, by default `access key` and `secret access key` |
| `credentialProcess` | `null` | any other command that prints the [credential_process JSON](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html), written as is |
| `settings` | `{}` | extra keys for the section, such as `sso_session`, `role_arn` or `source_profile`; they win over the ones above |

A profile sets `op` or `credentialProcess`, not both; an evaluation with both fails. One with neither gets its credentials from `settings` or from the environment.

```nix
dnix.aws = {
  enable = true;
  profiles = {
    default = { region = "us-east-1"; op = { vault = "Private"; item = "AWS personal"; }; };
    work = { region = "eu-west-1"; settings = { sso_session = "corp"; sso_account_id = "123456789012"; sso_role_name = "Dev"; }; };
  };
};
```

## Things to know

- **Each `op` profile runs `op` once per CLI call.** The AWS CLI does not cache a `credential_process` result between commands, so every `aws` invocation reads the item again: about 1.5 s, and a 1Password approval when the session has expired. Plain `op` with the desktop app's integration prompts on screen, so a run needs someone at the machine; nothing works headless.
- **A leftover `~/.aws/credentials` wins.** For the same profile, keys in that file come before `credential_process`. When moving from a module that rendered it, check the file is gone after the switch.
