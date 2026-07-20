const manifest = {"name":"MQTT Status"};
const API_VERSION = 2;
const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!internalAPIConnection) {
    throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
}
let api;
try {
    api = internalAPIConnection.connect(API_VERSION, manifest.name);
}
catch {
    api = internalAPIConnection.connect(1, manifest.name);
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
}
if (api._version != API_VERSION) {
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
}
const callable = api.callable;
const addEventListener = api.addEventListener;
const removeEventListener = api.removeEventListener;
const toaster = api.toaster;
const definePlugin = (fn) => {
    return (...args) => {
        return fn(...args);
    };
};

var DefaultContext = {
  color: undefined,
  size: undefined,
  className: undefined,
  style: undefined,
  attr: undefined
};
var IconContext = SP_REACT.createContext && /*#__PURE__*/SP_REACT.createContext(DefaultContext);

var _excluded = ["attr", "size", "title"];
function _objectWithoutProperties(e, t) { if (null == e) return {}; var o, r, i = _objectWithoutPropertiesLoose(e, t); if (Object.getOwnPropertySymbols) { var n = Object.getOwnPropertySymbols(e); for (r = 0; r < n.length; r++) o = n[r], -1 === t.indexOf(o) && {}.propertyIsEnumerable.call(e, o) && (i[o] = e[o]); } return i; }
function _objectWithoutPropertiesLoose(r, e) { if (null == r) return {}; var t = {}; for (var n in r) if ({}.hasOwnProperty.call(r, n)) { if (-1 !== e.indexOf(n)) continue; t[n] = r[n]; } return t; }
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function ownKeys(e, r) { var t = Object.keys(e); if (Object.getOwnPropertySymbols) { var o = Object.getOwnPropertySymbols(e); r && (o = o.filter(function (r) { return Object.getOwnPropertyDescriptor(e, r).enumerable; })), t.push.apply(t, o); } return t; }
function _objectSpread(e) { for (var r = 1; r < arguments.length; r++) { var t = null != arguments[r] ? arguments[r] : {}; r % 2 ? ownKeys(Object(t), true).forEach(function (r) { _defineProperty(e, r, t[r]); }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function (r) { Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(t, r)); }); } return e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == typeof i ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != typeof t || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r); if ("object" != typeof i) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function Tree2Element(tree) {
  return tree && tree.map((node, i) => /*#__PURE__*/SP_REACT.createElement(node.tag, _objectSpread({
    key: i
  }, node.attr), Tree2Element(node.child)));
}
function GenIcon(data) {
  return props => /*#__PURE__*/SP_REACT.createElement(IconBase, _extends({
    attr: _objectSpread({}, data.attr)
  }, props), Tree2Element(data.child));
}
function IconBase(props) {
  var elem = conf => {
    var attr = props.attr,
      size = props.size,
      title = props.title,
      svgProps = _objectWithoutProperties(props, _excluded);
    var computedSize = size || conf.size || "1em";
    var className;
    if (conf.className) className = conf.className;
    if (props.className) className = (className ? className + " " : "") + props.className;
    return /*#__PURE__*/SP_REACT.createElement("svg", _extends({
      stroke: "currentColor",
      fill: "currentColor",
      strokeWidth: "0"
    }, conf.attr, attr, svgProps, {
      className: className,
      style: _objectSpread(_objectSpread({
        color: props.color || conf.color
      }, conf.style), props.style),
      height: computedSize,
      width: computedSize,
      xmlns: "http://www.w3.org/2000/svg"
    }), title && /*#__PURE__*/SP_REACT.createElement("title", null, title), props.children);
  };
  return IconContext !== undefined ? /*#__PURE__*/SP_REACT.createElement(IconContext.Consumer, null, conf => elem(conf)) : elem(DefaultContext);
}

// THIS FILE IS AUTO GENERATED
function FaVolumeUp (props) {
  return GenIcon({"attr":{"viewBox":"0 0 576 512"},"child":[{"tag":"path","attr":{"d":"M215.03 71.05L126.06 160H24c-13.26 0-24 10.74-24 24v144c0 13.25 10.74 24 24 24h102.06l88.97 88.95c15.03 15.03 40.97 4.47 40.97-16.97V88.02c0-21.46-25.96-31.98-40.97-16.97zm233.32-51.08c-11.17-7.33-26.18-4.24-33.51 6.95-7.34 11.17-4.22 26.18 6.95 33.51 66.27 43.49 105.82 116.6 105.82 195.58 0 78.98-39.55 152.09-105.82 195.58-11.17 7.32-14.29 22.34-6.95 33.5 7.04 10.71 21.93 14.56 33.51 6.95C528.27 439.58 576 351.33 576 256S528.27 72.43 448.35 19.97zM480 256c0-63.53-32.06-121.94-85.77-156.24-11.19-7.14-26.03-3.82-33.12 7.46s-3.78 26.21 7.41 33.36C408.27 165.97 432 209.11 432 256s-23.73 90.03-63.48 115.42c-11.19 7.14-14.5 22.07-7.41 33.36 6.51 10.36 21.12 15.14 33.12 7.46C447.94 377.94 480 319.54 480 256zm-141.77-76.87c-11.58-6.33-26.19-2.16-32.61 9.45-6.39 11.61-2.16 26.2 9.45 32.61C327.98 228.28 336 241.63 336 256c0 14.38-8.02 27.72-20.92 34.81-11.61 6.41-15.84 21-9.45 32.61 6.43 11.66 21.05 15.8 32.61 9.45 28.23-15.55 45.77-45 45.77-76.88s-17.54-61.32-45.78-76.86z"},"child":[]}]})(props);
}

const getSettings = callable("get_settings");
const saveSettings = callable("save_settings");
const getConnectionStatus = callable("get_connection_status");
const getCurrentVolume = callable("get_current_volume");
const getCurrentStats = callable("get_current_stats");
const volumeButtonsGetState = callable("volume_buttons_get_state");
const volumeButtonsSet = callable("volume_buttons_set");
const wireplumberRestart = callable("wireplumber_restart");
function Content() {
    const [settings, setSettings] = SP_REACT.useState(null);
    const [status, setStatus] = SP_REACT.useState({ connected: false, error: null });
    const [volume, setVolume] = SP_REACT.useState(null);
    const [muted, setMuted] = SP_REACT.useState(null);
    const [stats, setStats] = SP_REACT.useState(null);
    const [buttonsEnabled, setButtonsEnabled] = SP_REACT.useState(false);
    const [buttonsMsg, setButtonsMsg] = SP_REACT.useState("");
    const [lastButton, setLastButton] = SP_REACT.useState("");
    const [lastGuideButton, setLastGuideButton] = SP_REACT.useState("");
    const [saving, setSaving] = SP_REACT.useState(false);
    SP_REACT.useEffect(() => {
        getSettings().then(setSettings);
        getConnectionStatus().then(setStatus);
        getCurrentVolume().then((v) => {
            setVolume(v.level);
            setMuted(v.muted);
        });
        getCurrentStats().then(setStats);
        volumeButtonsGetState().then((s) => {
            setButtonsEnabled(s.enabled);
        });
        const volumeListener = addEventListener("volume_changed", (level, isMuted) => {
            setVolume(level);
            setMuted(isMuted);
        });
        const statsListener = addEventListener("stats_update", (newStats) => {
            setStats(newStats);
        });
        const buttonListener = addEventListener("volume_button", (kind) => {
            setLastButton(kind);
        });
        const guideListener = addEventListener("guide_button", (kind) => {
            setLastGuideButton(kind);
        });
        const poll = setInterval(() => {
            getConnectionStatus().then(setStatus);
        }, 10000);
        return () => {
            removeEventListener("volume_changed", volumeListener);
            removeEventListener("stats_update", statsListener);
            removeEventListener("volume_button", buttonListener);
            removeEventListener("guide_button", guideListener);
            clearInterval(poll);
        };
    }, []);
    const updateSetting = (key, value) => {
        setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
    };
    const handleSave = async () => {
        if (!settings)
            return;
        setSaving(true);
        try {
            const updated = await saveSettings(settings);
            setSettings(updated);
            const newStatus = await getConnectionStatus();
            setStatus(newStatus);
            toaster.toast({ title: "MQTT", body: "Settings saved." });
        }
        finally {
            setSaving(false);
        }
    };
    const handleButtonsToggle = async (enabled) => {
        setButtonsEnabled(enabled);
        const result = await volumeButtonsSet(enabled);
        setButtonsEnabled(result.enabled);
        setButtonsMsg(result.output);
        toaster.toast({
            title: "Volume Buttons",
            body: result.ok
                ? enabled
                    ? "+/- buttons enabled."
                    : "Normal slider restored."
                : "Failed, see status.",
        });
    };
    const handleWireplumberRestart = async () => {
        const result = await wireplumberRestart();
        setButtonsMsg(result.output);
    };
    if (!settings) {
        return (SP_JSX.jsx(DFL.PanelSection, { children: SP_JSX.jsx(DFL.PanelSectionRow, { children: "Loading settings\u2026" }) }));
    }
    return (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsxs(DFL.PanelSection, { title: "Connection", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Status", children: status.connected ? "Connected" : status.error ? `Error: ${status.error}` : "Disconnected" }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Broker host", description: "IP or hostname of your MQTT broker (e.g. your Home Assistant server)", value: settings.mqtt_host, onChange: (e) => updateSetting("mqtt_host", e.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Port", value: String(settings.mqtt_port), onChange: (e) => updateSetting("mqtt_port", Number(e.target.value) || 1883) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Username", value: settings.mqtt_username, onChange: (e) => updateSetting("mqtt_username", e.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Password", description: "Stored in plain text in the plugin settings on this device", value: settings.mqtt_password, onChange: (e) => updateSetting("mqtt_password", e.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Use TLS", checked: settings.mqtt_use_tls, onChange: (value) => updateSetting("mqtt_use_tls", value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", onClick: handleSave, disabled: saving, children: saving ? "Saving…" : "Save & Connect" }) })] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Publishing", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Base topic", description: "All topics start with this prefix \u2014 remember it for automations", value: settings.mqtt_base_topic, onChange: (e) => updateSetting("mqtt_base_topic", e.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Device name (Home Assistant)", value: settings.device_name, onChange: (e) => updateSetting("device_name", e.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Interval (seconds)", value: settings.publish_interval, min: 5, max: 120, step: 5, showValue: true, onChange: (value) => updateSetting("publish_interval", value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Home Assistant discovery", description: "Automatically creates sensors and buttons in Home Assistant", checked: settings.ha_discovery, onChange: (value) => updateSetting("ha_discovery", value) }) })] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Live Status", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Volume", children: volume === null ? "n/a" : `${volume}%${muted ? " (muted)" : ""}` }) }), stats && (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "CPU", children: `${stats.cpu_percent}%` }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "RAM", children: `${stats.mem_percent}%` }) }), stats.gpu_busy_percent !== null && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "GPU", children: `${stats.gpu_busy_percent}%` }) })), stats.battery_percent !== null && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Battery", children: `${stats.battery_percent}%${stats.battery_charging ? " (charging)" : ""}` }) })), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Docked", children: stats.docked ? "Yes" : "No" }) })] })), lastGuideButton && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Last Guide press", children: lastGuideButton }) }))] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Volume Buttons (+/-)", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "+/- buttons & MQTT events", description: "Replaces the Game Mode volume slider with +/- buttons and publishes every press via MQTT (even at max volume or while muted)", checked: buttonsEnabled, onChange: handleButtonsToggle }) }), buttonsEnabled && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Last press", children: lastButton || "—" }) })), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", onClick: handleWireplumberRestart, children: "Restart audio service" }) }), buttonsMsg && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Status", children: buttonsMsg }) }))] })] }));
}
var index = definePlugin(() => {
    return {
        name: "MQTT Status",
        titleView: SP_JSX.jsx("div", { className: DFL.staticClasses.Title, children: "MQTT Status" }),
        content: SP_JSX.jsx(Content, {}),
        icon: SP_JSX.jsx(FaVolumeUp, {}),
        onDismount() { },
    };
});

export { index as default };
//# sourceMappingURL=index.js.map
