die() { echo "ha-mqtt: $*" >&2; exit 2; }

: "${HA_MQTT_HOST:?not set}"
: "${HA_MQTT_PASSWORD_FILE:?not set}"
PORT="${HA_MQTT_PORT:-1883}"
PREFIX="${HA_MQTT_DISCOVERY_PREFIX:-homeassistant}"
DEVICE_DEFAULT="${HA_MQTT_DEVICE:-$(id -un)}"
USER_NAME="${HA_MQTT_USER:-$(id -un)}"
MANUFACTURER="${HA_MQTT_DEVICE_MANUFACTURER:-}"
MODEL="${HA_MQTT_DEVICE_MODEL:-}"
PASSWORD="$(cat "$HA_MQTT_PASSWORD_FILE" 2>/dev/null)" || die "cannot read the broker password at $HA_MQTT_PASSWORD_FILE"

pub() {
  mosquitto_pub -h "$HA_MQTT_HOST" -p "$PORT" -u "$USER_NAME" -P "$PASSWORD" -q 1 -r -t "$1" -m "$2"
}

cmd_discover() {
  local component="${1:-}" object="${2:-}" device="$DEVICE_DEFAULT"
  local name="" device_class="" state_class="" unit="" icon="" entity_category=""
  local value_template="" with_attrs=0 device_name="" device_id="" suggested_area="" via_device=""
  local expire_after=""
  [ -n "$component" ] || die "discover: <component> required"
  [ -n "$object" ] || die "discover: <object> required"
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --name)            name="$2"; shift 2;;
      --device)          device="$2"; shift 2;;
      --device-name)     device_name="$2"; shift 2;;
      --device-id)       device_id="$2"; shift 2;;
      --suggested-area)  suggested_area="$2"; shift 2;;
      --via-device)      via_device="$2"; shift 2;;
      --device-class)    device_class="$2"; shift 2;;
      --state-class)     state_class="$2"; shift 2;;
      --unit)            unit="$2"; shift 2;;
      --icon)            icon="$2"; shift 2;;
      --entity-category) entity_category="$2"; shift 2;;
      --value-template)  value_template="$2"; shift 2;;
      --expire-after)    expire_after="$2"; shift 2;;
      --attrs)           with_attrs=1; shift;;
      *) die "discover: unknown option '$1'";;
    esac
  done

  local uid="${device}_${object}" payload
  payload="$(jq -nc \
    --arg name "${name:-$object}" --arg uid "$uid" \
    --arg st "${device}/${object}/state" --arg at "${device}/${object}/attrs" --arg ct "${device}/${object}/command" \
    --arg dc "$device_class" --arg sc "$state_class" --arg unit "$unit" --arg icon "$icon" \
    --arg ec "$entity_category" --arg vt "$value_template" --arg ea "$expire_after" --argjson attrs "$with_attrs" \
    --arg dev "${device_id:-$device}" --arg devname "${device_name:-$device}" \
    --arg manu "$MANUFACTURER" --arg model "$MODEL" --arg sa "$suggested_area" --arg vd "$via_device" \
    --arg comp "$component" '
      def opt($k; $v): if $v != "" then {($k): $v} else {} end;
      {
        name: $name, unique_id: $uid, object_id: $uid, state_topic: $st,
        device: ({ identifiers: [$dev], name: $devname }
          + opt("manufacturer"; $manu) + opt("model"; $model)
          + opt("suggested_area"; $sa) + opt("via_device"; $vd))
      }
      + opt("device_class"; $dc) + opt("state_class"; $sc) + opt("unit_of_measurement"; $unit)
      + opt("icon"; $icon) + opt("entity_category"; $ec) + opt("value_template"; $vt)
      + (if $ea != "" then {expire_after: ($ea | tonumber)} else {} end)
      + (if $attrs == 1 then {json_attributes_topic: $at} else {} end)
      + (if $comp == "switch" then {command_topic: $ct, optimistic: false} else {} end)
    ')"
  pub "${PREFIX}/${component}/${device}/${object}/config" "$payload"
}

cmd_state() {
  local object="${1:-}" device="$DEVICE_DEFAULT" value="" had_value=0 attrs_json=""
  local -a attr_kv=()
  [ -n "$object" ] || die "state: <object> required"
  shift
  if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then value="$1"; had_value=1; shift; fi
  while [ $# -gt 0 ]; do
    case "$1" in
      --device)     device="$2"; shift 2;;
      --value)      value="$2"; had_value=1; shift 2;;
      --now)        value="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"; had_value=1; shift;;
      --attr)       attr_kv+=("$2"); shift 2;;
      --attrs-json) attrs_json="$2"; shift 2;;
      *) die "state: unknown option '$1'";;
    esac
  done

  [ "$had_value" -eq 1 ] && pub "${device}/${object}/state" "$value"
  local ajson
  if [ -n "$attrs_json" ]; then
    ajson="$(printf '%s' "$attrs_json" | jq -c . 2>/dev/null)" || die "state: --attrs-json is not valid JSON"
    pub "${device}/${object}/attrs" "$ajson"
  elif [ "${#attr_kv[@]}" -gt 0 ]; then
    ajson="$(printf '%s\n' "${attr_kv[@]}" | jq -R -s -c '
      split("\n") | map(select(length > 0)) | map(
        (index("=")) as $i | { (.[:$i]): (.[$i+1:] as $v | ($v | tonumber? // $v)) }
      ) | add // {}')"
    pub "${device}/${object}/attrs" "$ajson"
  fi
}

cmd_undiscover() {
  local component="${1:-}" object="${2:-}" device="$DEVICE_DEFAULT"
  [ -n "$component" ] || die "undiscover: <component> required"
  [ -n "$object" ] || die "undiscover: <object> required"
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --device) device="$2"; shift 2;;
      *) die "undiscover: unknown option '$1'";;
    esac
  done
  pub "${PREFIX}/${component}/${device}/${object}/config" ""
  pub "${device}/${object}/state" ""
  pub "${device}/${object}/attrs" ""
}

case "${1:-}" in
  discover)   shift; cmd_discover "$@";;
  state)      shift; cmd_state "$@";;
  undiscover) shift; cmd_undiscover "$@";;
  ""|-h|--help|help) die "usage: ha-mqtt {discover <component> <object> [opts] | state <object> [value] [opts] | undiscover <component> <object> [--device D]}";;
  *) die "unknown verb '$1' (expected: discover | state | undiscover)";;
esac
