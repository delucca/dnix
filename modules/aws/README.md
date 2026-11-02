# aws

Render AWS CLI profiles in `~/.aws/config`, with credentials retrieved when a CLI or SDK needs them.
The Home Manager module installs the AWS CLI and leaves `~/.aws/credentials` unmanaged.

## Use

With [the dnix input available](../../README.md#use-a-module), add this to your Home Manager configuration:

```nix
{ inputs, ... }: {
  imports = [ inputs.dnix.homeManagerModules.aws ];
  dnix.aws = {
    enable = true;
    profiles.default.region = "us-east-1";
  };
}
```

This profile uses your existing credential environment or provider configuration.
For runtime retrieval, set either `profiles.<name>.op` with a 1Password vault and item, or `credentialProcess` with a command that emits [AWS credential-process JSON](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html).
Setting both fails evaluation. See [the option definitions](default.nix) for profile fields and custom settings.

## Credentials and precedence

- An `op` profile uses the [credential helper](credentials-op.sh) to read both key fields in one 1Password call. No retrieved key is written into the Nix configuration or a credentials file.
- The default key labels are `access key` and `secret access key`. You can override them per profile. The default `op` package is nixpkgs' unfree `_1password-cli`; your consumer must permit it when used.
- Credentials in a leftover `~/.aws/credentials` profile take precedence over `credential_process`. Check for old entries when migrating.
- The AWS CLI does not cache external process credentials between commands. Each invocation can require another 1Password read and, with desktop integration, an approval. Arrange authentication for the environment running the command.
- `settings` overrides generated section keys, including `region`, `output` and `credential_process`. Use it for SSO, role settings or an intentional override.
