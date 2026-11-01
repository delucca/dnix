if [ $# -ne 4 ]; then
  echo "usage: aws-credentials-op <vault> <item> <access key id field> <secret access key field>" >&2
  exit 2
fi

fields="$("$op" item get "$2" --vault "$1" --fields "label=$3,label=$4" --reveal --format json)"
jq -e --arg id "$3" --arg secret "$4" '
  (if type == "array" then . else [.] end) as $f
  | ($f | map(select(.label == $id)) | .[0].value // empty) as $kid
  | ($f | map(select(.label == $secret)) | .[0].value // empty) as $ksec
  | {Version: 1, AccessKeyId: $kid, SecretAccessKey: $ksec}
' <<<"$fields" || {
  echo "aws-credentials-op: item $2 in $1 lacks the fields \"$3\" and \"$4\"" >&2
  exit 1
}
