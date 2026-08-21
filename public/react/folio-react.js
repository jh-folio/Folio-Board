//#region \0rolldown/runtime.js
var e = (e, t) => () => (t || (e((t = { exports: {} }).exports, t), e = null), t.exports), t = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.portal"), r = Symbol.for("react.fragment"), i = Symbol.for("react.strict_mode"), a = Symbol.for("react.profiler"), o = Symbol.for("react.consumer"), s = Symbol.for("react.context"), c = Symbol.for("react.forward_ref"), l = Symbol.for("react.suspense"), u = Symbol.for("react.memo"), d = Symbol.for("react.lazy"), f = Symbol.for("react.activity"), p = Symbol.iterator;
	function m(e) {
		return typeof e != "object" || !e ? null : (e = p && e[p] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var h = {
		isMounted: function() {
			return !1;
		},
		enqueueForceUpdate: function() {},
		enqueueReplaceState: function() {},
		enqueueSetState: function() {}
	}, g = Object.assign, _ = {};
	function v(e, t, n) {
		this.props = e, this.context = t, this.refs = _, this.updater = n || h;
	}
	v.prototype.isReactComponent = {}, v.prototype.setState = function(e, t) {
		if (typeof e != "object" && typeof e != "function" && e != null) throw Error("takes an object of state variables to update or a function which returns an object of state variables.");
		this.updater.enqueueSetState(this, e, t, "setState");
	}, v.prototype.forceUpdate = function(e) {
		this.updater.enqueueForceUpdate(this, e, "forceUpdate");
	};
	function y() {}
	y.prototype = v.prototype;
	function b(e, t, n) {
		this.props = e, this.context = t, this.refs = _, this.updater = n || h;
	}
	var x = b.prototype = new y();
	x.constructor = b, g(x, v.prototype), x.isPureReactComponent = !0;
	var S = Array.isArray;
	function C() {}
	var w = {
		H: null,
		A: null,
		T: null,
		S: null
	}, T = Object.prototype.hasOwnProperty;
	function E(e, n, r) {
		var i = r.ref;
		return {
			$$typeof: t,
			type: e,
			key: n,
			ref: i === void 0 ? null : i,
			props: r
		};
	}
	function D(e, t) {
		return E(e.type, t, e.props);
	}
	function O(e) {
		return typeof e == "object" && !!e && e.$$typeof === t;
	}
	function k(e) {
		var t = {
			"=": "=0",
			":": "=2"
		};
		return "$" + e.replace(/[=:]/g, function(e) {
			return t[e];
		});
	}
	var A = /\/+/g;
	function j(e, t) {
		return typeof e == "object" && e && e.key != null ? k("" + e.key) : t.toString(36);
	}
	function M(e) {
		switch (e.status) {
			case "fulfilled": return e.value;
			case "rejected": throw e.reason;
			default: switch (typeof e.status == "string" ? e.then(C, C) : (e.status = "pending", e.then(function(t) {
				e.status === "pending" && (e.status = "fulfilled", e.value = t);
			}, function(t) {
				e.status === "pending" && (e.status = "rejected", e.reason = t);
			})), e.status) {
				case "fulfilled": return e.value;
				case "rejected": throw e.reason;
			}
		}
		throw e;
	}
	function N(e, r, i, a, o) {
		var s = typeof e;
		(s === "undefined" || s === "boolean") && (e = null);
		var c = !1;
		if (e === null) c = !0;
		else switch (s) {
			case "bigint":
			case "string":
			case "number":
				c = !0;
				break;
			case "object": switch (e.$$typeof) {
				case t:
				case n:
					c = !0;
					break;
				case d: return c = e._init, N(c(e._payload), r, i, a, o);
			}
		}
		if (c) return o = o(e), c = a === "" ? "." + j(e, 0) : a, S(o) ? (i = "", c != null && (i = c.replace(A, "$&/") + "/"), N(o, r, i, "", function(e) {
			return e;
		})) : o != null && (O(o) && (o = D(o, i + (o.key == null || e && e.key === o.key ? "" : ("" + o.key).replace(A, "$&/") + "/") + c)), r.push(o)), 1;
		c = 0;
		var l = a === "" ? "." : a + ":";
		if (S(e)) for (var u = 0; u < e.length; u++) a = e[u], s = l + j(a, u), c += N(a, r, i, s, o);
		else if (u = m(e), typeof u == "function") for (e = u.call(e), u = 0; !(a = e.next()).done;) a = a.value, s = l + j(a, u++), c += N(a, r, i, s, o);
		else if (s === "object") {
			if (typeof e.then == "function") return N(M(e), r, i, a, o);
			throw r = String(e), Error("Objects are not valid as a React child (found: " + (r === "[object Object]" ? "object with keys {" + Object.keys(e).join(", ") + "}" : r) + "). If you meant to render a collection of children, use an array instead.");
		}
		return c;
	}
	function P(e, t, n) {
		if (e == null) return e;
		var r = [], i = 0;
		return N(e, r, "", "", function(e) {
			return t.call(n, e, i++);
		}), r;
	}
	function F(e) {
		if (e._status === -1) {
			var t = e._result;
			t = t(), t.then(function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 1, e._result = t);
			}, function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 2, e._result = t);
			}), e._status === -1 && (e._status = 0, e._result = t);
		}
		if (e._status === 1) return e._result.default;
		throw e._result;
	}
	var I = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	}, L = {
		map: P,
		forEach: function(e, t, n) {
			P(e, function() {
				t.apply(this, arguments);
			}, n);
		},
		count: function(e) {
			var t = 0;
			return P(e, function() {
				t++;
			}), t;
		},
		toArray: function(e) {
			return P(e, function(e) {
				return e;
			}) || [];
		},
		only: function(e) {
			if (!O(e)) throw Error("React.Children.only expected to receive a single React element child.");
			return e;
		}
	};
	e.Activity = f, e.Children = L, e.Component = v, e.Fragment = r, e.Profiler = a, e.PureComponent = b, e.StrictMode = i, e.Suspense = l, e.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = w, e.__COMPILER_RUNTIME = {
		__proto__: null,
		c: function(e) {
			return w.H.useMemoCache(e);
		}
	}, e.cache = function(e) {
		return function() {
			return e.apply(null, arguments);
		};
	}, e.cacheSignal = function() {
		return null;
	}, e.cloneElement = function(e, t, n) {
		if (e == null) throw Error("The argument must be a React element, but you passed " + e + ".");
		var r = g({}, e.props), i = e.key;
		if (t != null) for (a in t.key !== void 0 && (i = "" + t.key), t) !T.call(t, a) || a === "key" || a === "__self" || a === "__source" || a === "ref" && t.ref === void 0 || (r[a] = t[a]);
		var a = arguments.length - 2;
		if (a === 1) r.children = n;
		else if (1 < a) {
			for (var o = Array(a), s = 0; s < a; s++) o[s] = arguments[s + 2];
			r.children = o;
		}
		return E(e.type, i, r);
	}, e.createContext = function(e) {
		return e = {
			$$typeof: s,
			_currentValue: e,
			_currentValue2: e,
			_threadCount: 0,
			Provider: null,
			Consumer: null
		}, e.Provider = e, e.Consumer = {
			$$typeof: o,
			_context: e
		}, e;
	}, e.createElement = function(e, t, n) {
		var r, i = {}, a = null;
		if (t != null) for (r in t.key !== void 0 && (a = "" + t.key), t) T.call(t, r) && r !== "key" && r !== "__self" && r !== "__source" && (i[r] = t[r]);
		var o = arguments.length - 2;
		if (o === 1) i.children = n;
		else if (1 < o) {
			for (var s = Array(o), c = 0; c < o; c++) s[c] = arguments[c + 2];
			i.children = s;
		}
		if (e && e.defaultProps) for (r in o = e.defaultProps, o) i[r] === void 0 && (i[r] = o[r]);
		return E(e, a, i);
	}, e.createRef = function() {
		return { current: null };
	}, e.forwardRef = function(e) {
		return {
			$$typeof: c,
			render: e
		};
	}, e.isValidElement = O, e.lazy = function(e) {
		return {
			$$typeof: d,
			_payload: {
				_status: -1,
				_result: e
			},
			_init: F
		};
	}, e.memo = function(e, t) {
		return {
			$$typeof: u,
			type: e,
			compare: t === void 0 ? null : t
		};
	}, e.startTransition = function(e) {
		var t = w.T, n = {};
		w.T = n;
		try {
			var r = e(), i = w.S;
			i !== null && i(n, r), typeof r == "object" && r && typeof r.then == "function" && r.then(C, I);
		} catch (e) {
			I(e);
		} finally {
			t !== null && n.types !== null && (t.types = n.types), w.T = t;
		}
	}, e.unstable_useCacheRefresh = function() {
		return w.H.useCacheRefresh();
	}, e.use = function(e) {
		return w.H.use(e);
	}, e.useActionState = function(e, t, n) {
		return w.H.useActionState(e, t, n);
	}, e.useCallback = function(e, t) {
		return w.H.useCallback(e, t);
	}, e.useContext = function(e) {
		return w.H.useContext(e);
	}, e.useDebugValue = function() {}, e.useDeferredValue = function(e, t) {
		return w.H.useDeferredValue(e, t);
	}, e.useEffect = function(e, t) {
		return w.H.useEffect(e, t);
	}, e.useEffectEvent = function(e) {
		return w.H.useEffectEvent(e);
	}, e.useId = function() {
		return w.H.useId();
	}, e.useImperativeHandle = function(e, t, n) {
		return w.H.useImperativeHandle(e, t, n);
	}, e.useInsertionEffect = function(e, t) {
		return w.H.useInsertionEffect(e, t);
	}, e.useLayoutEffect = function(e, t) {
		return w.H.useLayoutEffect(e, t);
	}, e.useMemo = function(e, t) {
		return w.H.useMemo(e, t);
	}, e.useOptimistic = function(e, t) {
		return w.H.useOptimistic(e, t);
	}, e.useReducer = function(e, t, n) {
		return w.H.useReducer(e, t, n);
	}, e.useRef = function(e) {
		return w.H.useRef(e);
	}, e.useState = function(e) {
		return w.H.useState(e);
	}, e.useSyncExternalStore = function(e, t, n) {
		return w.H.useSyncExternalStore(e, t, n);
	}, e.useTransition = function() {
		return w.H.useTransition();
	}, e.version = "19.2.8";
})), n = /* @__PURE__ */ e(((e, n) => {
	n.exports = t();
})), r = /* @__PURE__ */ e(((e) => {
	function t(e, t) {
		var n = e.length;
		e.push(t);
		a: for (; 0 < n;) {
			var r = n - 1 >>> 1, a = e[r];
			if (0 < i(a, t)) e[r] = t, e[n] = a, n = r;
			else break a;
		}
	}
	function n(e) {
		return e.length === 0 ? null : e[0];
	}
	function r(e) {
		if (e.length === 0) return null;
		var t = e[0], n = e.pop();
		if (n !== t) {
			e[0] = n;
			a: for (var r = 0, a = e.length, o = a >>> 1; r < o;) {
				var s = 2 * (r + 1) - 1, c = e[s], l = s + 1, u = e[l];
				if (0 > i(c, n)) l < a && 0 > i(u, c) ? (e[r] = u, e[l] = n, r = l) : (e[r] = c, e[s] = n, r = s);
				else if (l < a && 0 > i(u, n)) e[r] = u, e[l] = n, r = l;
				else break a;
			}
		}
		return t;
	}
	function i(e, t) {
		var n = e.sortIndex - t.sortIndex;
		return n === 0 ? e.id - t.id : n;
	}
	if (e.unstable_now = void 0, typeof performance == "object" && typeof performance.now == "function") {
		var a = performance;
		e.unstable_now = function() {
			return a.now();
		};
	} else {
		var o = Date, s = o.now();
		e.unstable_now = function() {
			return o.now() - s;
		};
	}
	var c = [], l = [], u = 1, d = null, f = 3, p = !1, m = !1, h = !1, g = !1, _ = typeof setTimeout == "function" ? setTimeout : null, v = typeof clearTimeout == "function" ? clearTimeout : null, y = typeof setImmediate < "u" ? setImmediate : null;
	function b(e) {
		for (var i = n(l); i !== null;) {
			if (i.callback === null) r(l);
			else if (i.startTime <= e) r(l), i.sortIndex = i.expirationTime, t(c, i);
			else break;
			i = n(l);
		}
	}
	function x(e) {
		if (h = !1, b(e), !m) if (n(c) !== null) m = !0, S || (S = !0, O());
		else {
			var t = n(l);
			t !== null && j(x, t.startTime - e);
		}
	}
	var S = !1, C = -1, w = 5, T = -1;
	function E() {
		return g ? !0 : !(e.unstable_now() - T < w);
	}
	function D() {
		if (g = !1, S) {
			var t = e.unstable_now();
			T = t;
			var i = !0;
			try {
				a: {
					m = !1, h && (h = !1, v(C), C = -1), p = !0;
					var a = f;
					try {
						b: {
							for (b(t), d = n(c); d !== null && !(d.expirationTime > t && E());) {
								var o = d.callback;
								if (typeof o == "function") {
									d.callback = null, f = d.priorityLevel;
									var s = o(d.expirationTime <= t);
									if (t = e.unstable_now(), typeof s == "function") {
										d.callback = s, b(t), i = !0;
										break b;
									}
									d === n(c) && r(c), b(t);
								} else r(c);
								d = n(c);
							}
							if (d !== null) i = !0;
							else {
								var u = n(l);
								u !== null && j(x, u.startTime - t), i = !1;
							}
						}
						break a;
					} finally {
						d = null, f = a, p = !1;
					}
				}
			} finally {
				i ? O() : S = !1;
			}
		}
	}
	var O;
	if (typeof y == "function") O = function() {
		y(D);
	};
	else if (typeof MessageChannel < "u") {
		var k = new MessageChannel(), A = k.port2;
		k.port1.onmessage = D, O = function() {
			A.postMessage(null);
		};
	} else O = function() {
		_(D, 0);
	};
	function j(t, n) {
		C = _(function() {
			t(e.unstable_now());
		}, n);
	}
	e.unstable_IdlePriority = 5, e.unstable_ImmediatePriority = 1, e.unstable_LowPriority = 4, e.unstable_NormalPriority = 3, e.unstable_Profiling = null, e.unstable_UserBlockingPriority = 2, e.unstable_cancelCallback = function(e) {
		e.callback = null;
	}, e.unstable_forceFrameRate = function(e) {
		0 > e || 125 < e ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : w = 0 < e ? Math.floor(1e3 / e) : 5;
	}, e.unstable_getCurrentPriorityLevel = function() {
		return f;
	}, e.unstable_next = function(e) {
		switch (f) {
			case 1:
			case 2:
			case 3:
				var t = 3;
				break;
			default: t = f;
		}
		var n = f;
		f = t;
		try {
			return e();
		} finally {
			f = n;
		}
	}, e.unstable_requestPaint = function() {
		g = !0;
	}, e.unstable_runWithPriority = function(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 3:
			case 4:
			case 5: break;
			default: e = 3;
		}
		var n = f;
		f = e;
		try {
			return t();
		} finally {
			f = n;
		}
	}, e.unstable_scheduleCallback = function(r, i, a) {
		var o = e.unstable_now();
		switch (typeof a == "object" && a ? (a = a.delay, a = typeof a == "number" && 0 < a ? o + a : o) : a = o, r) {
			case 1:
				var s = -1;
				break;
			case 2:
				s = 250;
				break;
			case 5:
				s = 1073741823;
				break;
			case 4:
				s = 1e4;
				break;
			default: s = 5e3;
		}
		return s = a + s, r = {
			id: u++,
			callback: i,
			priorityLevel: r,
			startTime: a,
			expirationTime: s,
			sortIndex: -1
		}, a > o ? (r.sortIndex = a, t(l, r), n(c) === null && r === n(l) && (h ? (v(C), C = -1) : h = !0, j(x, a - o))) : (r.sortIndex = s, t(c, r), m || p || (m = !0, S || (S = !0, O()))), r;
	}, e.unstable_shouldYield = E, e.unstable_wrapCallback = function(e) {
		var t = f;
		return function() {
			var n = f;
			f = t;
			try {
				return e.apply(this, arguments);
			} finally {
				f = n;
			}
		};
	};
})), i = /* @__PURE__ */ e(((e, t) => {
	t.exports = r();
})), a = /* @__PURE__ */ e(((e) => {
	var t = n();
	function r(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function i() {}
	var a = {
		d: {
			f: i,
			r: function() {
				throw Error(r(522));
			},
			D: i,
			C: i,
			L: i,
			m: i,
			X: i,
			S: i,
			M: i
		},
		p: 0,
		findDOMNode: null
	}, o = Symbol.for("react.portal");
	function s(e, t, n) {
		var r = 3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
		return {
			$$typeof: o,
			key: r == null ? null : "" + r,
			children: e,
			containerInfo: t,
			implementation: n
		};
	}
	var c = t.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
	function l(e, t) {
		if (e === "font") return "";
		if (typeof t == "string") return t === "use-credentials" ? t : "";
	}
	e.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = a, e.createPortal = function(e, t) {
		var n = 2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
		if (!t || t.nodeType !== 1 && t.nodeType !== 9 && t.nodeType !== 11) throw Error(r(299));
		return s(e, t, null, n);
	}, e.flushSync = function(e) {
		var t = c.T, n = a.p;
		try {
			if (c.T = null, a.p = 2, e) return e();
		} finally {
			c.T = t, a.p = n, a.d.f();
		}
	}, e.preconnect = function(e, t) {
		typeof e == "string" && (t ? (t = t.crossOrigin, t = typeof t == "string" ? t === "use-credentials" ? t : "" : void 0) : t = null, a.d.C(e, t));
	}, e.prefetchDNS = function(e) {
		typeof e == "string" && a.d.D(e);
	}, e.preinit = function(e, t) {
		if (typeof e == "string" && t && typeof t.as == "string") {
			var n = t.as, r = l(n, t.crossOrigin), i = typeof t.integrity == "string" ? t.integrity : void 0, o = typeof t.fetchPriority == "string" ? t.fetchPriority : void 0;
			n === "style" ? a.d.S(e, typeof t.precedence == "string" ? t.precedence : void 0, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o
			}) : n === "script" && a.d.X(e, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0
			});
		}
	}, e.preinitModule = function(e, t) {
		if (typeof e == "string") if (typeof t == "object" && t) {
			if (t.as == null || t.as === "script") {
				var n = l(t.as, t.crossOrigin);
				a.d.M(e, {
					crossOrigin: n,
					integrity: typeof t.integrity == "string" ? t.integrity : void 0,
					nonce: typeof t.nonce == "string" ? t.nonce : void 0
				});
			}
		} else t ?? a.d.M(e);
	}, e.preload = function(e, t) {
		if (typeof e == "string" && typeof t == "object" && t && typeof t.as == "string") {
			var n = t.as, r = l(n, t.crossOrigin);
			a.d.L(e, n, {
				crossOrigin: r,
				integrity: typeof t.integrity == "string" ? t.integrity : void 0,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0,
				type: typeof t.type == "string" ? t.type : void 0,
				fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0,
				referrerPolicy: typeof t.referrerPolicy == "string" ? t.referrerPolicy : void 0,
				imageSrcSet: typeof t.imageSrcSet == "string" ? t.imageSrcSet : void 0,
				imageSizes: typeof t.imageSizes == "string" ? t.imageSizes : void 0,
				media: typeof t.media == "string" ? t.media : void 0
			});
		}
	}, e.preloadModule = function(e, t) {
		if (typeof e == "string") if (t) {
			var n = l(t.as, t.crossOrigin);
			a.d.m(e, {
				as: typeof t.as == "string" && t.as !== "script" ? t.as : void 0,
				crossOrigin: n,
				integrity: typeof t.integrity == "string" ? t.integrity : void 0
			});
		} else a.d.m(e);
	}, e.requestFormReset = function(e) {
		a.d.r(e);
	}, e.unstable_batchedUpdates = function(e, t) {
		return e(t);
	}, e.useFormState = function(e, t, n) {
		return c.H.useFormState(e, t, n);
	}, e.useFormStatus = function() {
		return c.H.useHostTransitionStatus();
	}, e.version = "19.2.8";
})), o = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function")) try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = a();
})), s = /* @__PURE__ */ e(((e) => {
	var t = i(), r = n(), a = o();
	function s(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function c(e) {
		return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11);
	}
	function l(e) {
		var t = e, n = e;
		if (e.alternate) for (; t.return;) t = t.return;
		else {
			e = t;
			do
				t = e, t.flags & 4098 && (n = t.return), e = t.return;
			while (e);
		}
		return t.tag === 3 ? n : null;
	}
	function u(e) {
		if (e.tag === 13) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function d(e) {
		if (e.tag === 31) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function f(e) {
		if (l(e) !== e) throw Error(s(188));
	}
	function p(e) {
		var t = e.alternate;
		if (!t) {
			if (t = l(e), t === null) throw Error(s(188));
			return t === e ? e : null;
		}
		for (var n = e, r = t;;) {
			var i = n.return;
			if (i === null) break;
			var a = i.alternate;
			if (a === null) {
				if (r = i.return, r !== null) {
					n = r;
					continue;
				}
				break;
			}
			if (i.child === a.child) {
				for (a = i.child; a;) {
					if (a === n) return f(i), e;
					if (a === r) return f(i), t;
					a = a.sibling;
				}
				throw Error(s(188));
			}
			if (n.return !== r.return) n = i, r = a;
			else {
				for (var o = !1, c = i.child; c;) {
					if (c === n) {
						o = !0, n = i, r = a;
						break;
					}
					if (c === r) {
						o = !0, r = i, n = a;
						break;
					}
					c = c.sibling;
				}
				if (!o) {
					for (c = a.child; c;) {
						if (c === n) {
							o = !0, n = a, r = i;
							break;
						}
						if (c === r) {
							o = !0, r = a, n = i;
							break;
						}
						c = c.sibling;
					}
					if (!o) throw Error(s(189));
				}
			}
			if (n.alternate !== r) throw Error(s(190));
		}
		if (n.tag !== 3) throw Error(s(188));
		return n.stateNode.current === n ? e : t;
	}
	function m(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e;
		for (e = e.child; e !== null;) {
			if (t = m(e), t !== null) return t;
			e = e.sibling;
		}
		return null;
	}
	var h = Object.assign, g = Symbol.for("react.element"), _ = Symbol.for("react.transitional.element"), v = Symbol.for("react.portal"), y = Symbol.for("react.fragment"), b = Symbol.for("react.strict_mode"), x = Symbol.for("react.profiler"), S = Symbol.for("react.consumer"), C = Symbol.for("react.context"), w = Symbol.for("react.forward_ref"), T = Symbol.for("react.suspense"), E = Symbol.for("react.suspense_list"), D = Symbol.for("react.memo"), O = Symbol.for("react.lazy"), k = Symbol.for("react.activity"), A = Symbol.for("react.memo_cache_sentinel"), j = Symbol.iterator;
	function M(e) {
		return typeof e != "object" || !e ? null : (e = j && e[j] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var N = Symbol.for("react.client.reference");
	function P(e) {
		if (e == null) return null;
		if (typeof e == "function") return e.$$typeof === N ? null : e.displayName || e.name || null;
		if (typeof e == "string") return e;
		switch (e) {
			case y: return "Fragment";
			case x: return "Profiler";
			case b: return "StrictMode";
			case T: return "Suspense";
			case E: return "SuspenseList";
			case k: return "Activity";
		}
		if (typeof e == "object") switch (e.$$typeof) {
			case v: return "Portal";
			case C: return e.displayName || "Context";
			case S: return (e._context.displayName || "Context") + ".Consumer";
			case w:
				var t = e.render;
				return e = e.displayName, e ||= (e = t.displayName || t.name || "", e === "" ? "ForwardRef" : "ForwardRef(" + e + ")"), e;
			case D: return t = e.displayName || null, t === null ? P(e.type) || "Memo" : t;
			case O:
				t = e._payload, e = e._init;
				try {
					return P(e(t));
				} catch {}
		}
		return null;
	}
	var F = Array.isArray, I = r.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, L = a.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, R = {
		pending: !1,
		data: null,
		method: null,
		action: null
	}, z = [], B = -1;
	function V(e) {
		return { current: e };
	}
	function H(e) {
		0 > B || (e.current = z[B], z[B] = null, B--);
	}
	function U(e, t) {
		B++, z[B] = e.current, e.current = t;
	}
	var ee = V(null), te = V(null), W = V(null), G = V(null);
	function K(e, t) {
		switch (U(W, t), U(te, e), U(ee, null), t.nodeType) {
			case 9:
			case 11:
				e = (e = t.documentElement) && (e = e.namespaceURI) ? Vd(e) : 0;
				break;
			default: if (e = t.tagName, t = t.namespaceURI) t = Vd(t), e = Hd(t, e);
			else switch (e) {
				case "svg":
					e = 1;
					break;
				case "math":
					e = 2;
					break;
				default: e = 0;
			}
		}
		H(ee), U(ee, e);
	}
	function q() {
		H(ee), H(te), H(W);
	}
	function ne(e) {
		e.memoizedState !== null && U(G, e);
		var t = ee.current, n = Hd(t, e.type);
		t !== n && (U(te, e), U(ee, n));
	}
	function re(e) {
		te.current === e && (H(ee), H(te)), G.current === e && (H(G), Qf._currentValue = R);
	}
	var ie, ae;
	function oe(e) {
		if (ie === void 0) try {
			throw Error();
		} catch (e) {
			var t = e.stack.trim().match(/\n( *(at )?)/);
			ie = t && t[1] || "", ae = -1 < e.stack.indexOf("\n    at") ? " (<anonymous>)" : -1 < e.stack.indexOf("@") ? "@unknown:0:0" : "";
		}
		return "\n" + ie + e + ae;
	}
	var se = !1;
	function ce(e, t) {
		if (!e || se) return "";
		se = !0;
		var n = Error.prepareStackTrace;
		Error.prepareStackTrace = void 0;
		try {
			var r = { DetermineComponentFrameRoot: function() {
				try {
					if (t) {
						var n = function() {
							throw Error();
						};
						if (Object.defineProperty(n.prototype, "props", { set: function() {
							throw Error();
						} }), typeof Reflect == "object" && Reflect.construct) {
							try {
								Reflect.construct(n, []);
							} catch (e) {
								var r = e;
							}
							Reflect.construct(e, [], n);
						} else {
							try {
								n.call();
							} catch (e) {
								r = e;
							}
							e.call(n.prototype);
						}
					} else {
						try {
							throw Error();
						} catch (e) {
							r = e;
						}
						(n = e()) && typeof n.catch == "function" && n.catch(function() {});
					}
				} catch (e) {
					if (e && r && typeof e.stack == "string") return [e.stack, r.stack];
				}
				return [null, null];
			} };
			r.DetermineComponentFrameRoot.displayName = "DetermineComponentFrameRoot";
			var i = Object.getOwnPropertyDescriptor(r.DetermineComponentFrameRoot, "name");
			i && i.configurable && Object.defineProperty(r.DetermineComponentFrameRoot, "name", { value: "DetermineComponentFrameRoot" });
			var a = r.DetermineComponentFrameRoot(), o = a[0], s = a[1];
			if (o && s) {
				var c = o.split("\n"), l = s.split("\n");
				for (i = r = 0; r < c.length && !c[r].includes("DetermineComponentFrameRoot");) r++;
				for (; i < l.length && !l[i].includes("DetermineComponentFrameRoot");) i++;
				if (r === c.length || i === l.length) for (r = c.length - 1, i = l.length - 1; 1 <= r && 0 <= i && c[r] !== l[i];) i--;
				for (; 1 <= r && 0 <= i; r--, i--) if (c[r] !== l[i]) {
					if (r !== 1 || i !== 1) do
						if (r--, i--, 0 > i || c[r] !== l[i]) {
							var u = "\n" + c[r].replace(" at new ", " at ");
							return e.displayName && u.includes("<anonymous>") && (u = u.replace("<anonymous>", e.displayName)), u;
						}
					while (1 <= r && 0 <= i);
					break;
				}
			}
		} finally {
			se = !1, Error.prepareStackTrace = n;
		}
		return (n = e ? e.displayName || e.name : "") ? oe(n) : "";
	}
	function le(e, t) {
		switch (e.tag) {
			case 26:
			case 27:
			case 5: return oe(e.type);
			case 16: return oe("Lazy");
			case 13: return e.child !== t && t !== null ? oe("Suspense Fallback") : oe("Suspense");
			case 19: return oe("SuspenseList");
			case 0:
			case 15: return ce(e.type, !1);
			case 11: return ce(e.type.render, !1);
			case 1: return ce(e.type, !0);
			case 31: return oe("Activity");
			default: return "";
		}
	}
	function ue(e) {
		try {
			var t = "", n = null;
			do
				t += le(e, n), n = e, e = e.return;
			while (e);
			return t;
		} catch (e) {
			return "\nError generating stack: " + e.message + "\n" + e.stack;
		}
	}
	var de = Object.prototype.hasOwnProperty, fe = t.unstable_scheduleCallback, pe = t.unstable_cancelCallback, me = t.unstable_shouldYield, he = t.unstable_requestPaint, ge = t.unstable_now, _e = t.unstable_getCurrentPriorityLevel, ve = t.unstable_ImmediatePriority, ye = t.unstable_UserBlockingPriority, be = t.unstable_NormalPriority, xe = t.unstable_LowPriority, Se = t.unstable_IdlePriority, Ce = t.log, we = t.unstable_setDisableYieldValue, Te = null, Ee = null;
	function De(e) {
		if (typeof Ce == "function" && we(e), Ee && typeof Ee.setStrictMode == "function") try {
			Ee.setStrictMode(Te, e);
		} catch {}
	}
	var Oe = Math.clz32 ? Math.clz32 : je, ke = Math.log, Ae = Math.LN2;
	function je(e) {
		return e >>>= 0, e === 0 ? 32 : 31 - (ke(e) / Ae | 0) | 0;
	}
	var Me = 256, Ne = 262144, Pe = 4194304;
	function Fe(e) {
		var t = e & 42;
		if (t !== 0) return t;
		switch (e & -e) {
			case 1: return 1;
			case 2: return 2;
			case 4: return 4;
			case 8: return 8;
			case 16: return 16;
			case 32: return 32;
			case 64: return 64;
			case 128: return 128;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072: return e & 261888;
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return e & 3932160;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return e & 62914560;
			case 67108864: return 67108864;
			case 134217728: return 134217728;
			case 268435456: return 268435456;
			case 536870912: return 536870912;
			case 1073741824: return 0;
			default: return e;
		}
	}
	function Ie(e, t, n) {
		var r = e.pendingLanes;
		if (r === 0) return 0;
		var i = 0, a = e.suspendedLanes, o = e.pingedLanes;
		e = e.warmLanes;
		var s = r & 134217727;
		return s === 0 ? (s = r & ~a, s === 0 ? o === 0 ? n || (n = r & ~e, n !== 0 && (i = Fe(n))) : i = Fe(o) : i = Fe(s)) : (r = s & ~a, r === 0 ? (o &= s, o === 0 ? n || (n = s & ~e, n !== 0 && (i = Fe(n))) : i = Fe(o)) : i = Fe(r)), i === 0 ? 0 : t !== 0 && t !== i && (t & a) === 0 && (a = i & -i, n = t & -t, a >= n || a === 32 && n & 4194048) ? t : i;
	}
	function Le(e, t) {
		return (e.pendingLanes & ~(e.suspendedLanes & ~e.pingedLanes) & t) === 0;
	}
	function Re(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 4:
			case 8:
			case 64: return t + 250;
			case 16:
			case 32:
			case 128:
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return t + 5e3;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return -1;
			case 67108864:
			case 134217728:
			case 268435456:
			case 536870912:
			case 1073741824: return -1;
			default: return -1;
		}
	}
	function ze() {
		var e = Pe;
		return Pe <<= 1, !(Pe & 62914560) && (Pe = 4194304), e;
	}
	function Be(e) {
		for (var t = [], n = 0; 31 > n; n++) t.push(e);
		return t;
	}
	function Ve(e, t) {
		e.pendingLanes |= t, t !== 268435456 && (e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0);
	}
	function He(e, t, n, r, i, a) {
		var o = e.pendingLanes;
		e.pendingLanes = n, e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0, e.expiredLanes &= n, e.entangledLanes &= n, e.errorRecoveryDisabledLanes &= n, e.shellSuspendCounter = 0;
		var s = e.entanglements, c = e.expirationTimes, l = e.hiddenUpdates;
		for (n = o & ~n; 0 < n;) {
			var u = 31 - Oe(n), d = 1 << u;
			s[u] = 0, c[u] = -1;
			var f = l[u];
			if (f !== null) for (l[u] = null, u = 0; u < f.length; u++) {
				var p = f[u];
				p !== null && (p.lane &= -536870913);
			}
			n &= ~d;
		}
		r !== 0 && Ue(e, r, 0), a !== 0 && i === 0 && e.tag !== 0 && (e.suspendedLanes |= a & ~(o & ~t));
	}
	function Ue(e, t, n) {
		e.pendingLanes |= t, e.suspendedLanes &= ~t;
		var r = 31 - Oe(t);
		e.entangledLanes |= t, e.entanglements[r] = e.entanglements[r] | 1073741824 | n & 261930;
	}
	function We(e, t) {
		var n = e.entangledLanes |= t;
		for (e = e.entanglements; n;) {
			var r = 31 - Oe(n), i = 1 << r;
			i & t | e[r] & t && (e[r] |= t), n &= ~i;
		}
	}
	function Ge(e, t) {
		var n = t & -t;
		return n = n & 42 ? 1 : Ke(n), (n & (e.suspendedLanes | t)) === 0 ? n : 0;
	}
	function Ke(e) {
		switch (e) {
			case 2:
				e = 1;
				break;
			case 8:
				e = 4;
				break;
			case 32:
				e = 16;
				break;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152:
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432:
				e = 128;
				break;
			case 268435456:
				e = 134217728;
				break;
			default: e = 0;
		}
		return e;
	}
	function qe(e) {
		return e &= -e, 2 < e ? 8 < e ? e & 134217727 ? 32 : 268435456 : 8 : 2;
	}
	function Je() {
		var e = L.p;
		return e === 0 ? (e = window.event, e === void 0 ? 32 : mp(e.type)) : e;
	}
	function Ye(e, t) {
		var n = L.p;
		try {
			return L.p = e, t();
		} finally {
			L.p = n;
		}
	}
	var Xe = Math.random().toString(36).slice(2), Ze = "__reactFiber$" + Xe, Qe = "__reactProps$" + Xe, $e = "__reactContainer$" + Xe, et = "__reactEvents$" + Xe, tt = "__reactListeners$" + Xe, nt = "__reactHandles$" + Xe, rt = "__reactResources$" + Xe, it = "__reactMarker$" + Xe;
	function at(e) {
		delete e[Ze], delete e[Qe], delete e[et], delete e[tt], delete e[nt];
	}
	function ot(e) {
		var t = e[Ze];
		if (t) return t;
		for (var n = e.parentNode; n;) {
			if (t = n[$e] || n[Ze]) {
				if (n = t.alternate, t.child !== null || n !== null && n.child !== null) for (e = df(e); e !== null;) {
					if (n = e[Ze]) return n;
					e = df(e);
				}
				return t;
			}
			e = n, n = e.parentNode;
		}
		return null;
	}
	function st(e) {
		if (e = e[Ze] || e[$e]) {
			var t = e.tag;
			if (t === 5 || t === 6 || t === 13 || t === 31 || t === 26 || t === 27 || t === 3) return e;
		}
		return null;
	}
	function ct(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e.stateNode;
		throw Error(s(33));
	}
	function lt(e) {
		var t = e[rt];
		return t ||= e[rt] = {
			hoistableStyles: /* @__PURE__ */ new Map(),
			hoistableScripts: /* @__PURE__ */ new Map()
		}, t;
	}
	function ut(e) {
		e[it] = !0;
	}
	var dt = /* @__PURE__ */ new Set(), ft = {};
	function pt(e, t) {
		mt(e, t), mt(e + "Capture", t);
	}
	function mt(e, t) {
		for (ft[e] = t, e = 0; e < t.length; e++) dt.add(t[e]);
	}
	var ht = RegExp("^[:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD][:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD\\-.0-9\\u00B7\\u0300-\\u036F\\u203F-\\u2040]*$"), gt = {}, _t = {};
	function vt(e) {
		return de.call(_t, e) ? !0 : de.call(gt, e) ? !1 : ht.test(e) ? _t[e] = !0 : (gt[e] = !0, !1);
	}
	function yt(e, t, n) {
		if (vt(t)) if (n === null) e.removeAttribute(t);
		else {
			switch (typeof n) {
				case "undefined":
				case "function":
				case "symbol":
					e.removeAttribute(t);
					return;
				case "boolean":
					var r = t.toLowerCase().slice(0, 5);
					if (r !== "data-" && r !== "aria-") {
						e.removeAttribute(t);
						return;
					}
			}
			e.setAttribute(t, "" + n);
		}
	}
	function bt(e, t, n) {
		if (n === null) e.removeAttribute(t);
		else {
			switch (typeof n) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(t);
					return;
			}
			e.setAttribute(t, "" + n);
		}
	}
	function xt(e, t, n, r) {
		if (r === null) e.removeAttribute(n);
		else {
			switch (typeof r) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(n);
					return;
			}
			e.setAttributeNS(t, n, "" + r);
		}
	}
	function St(e) {
		switch (typeof e) {
			case "bigint":
			case "boolean":
			case "number":
			case "string":
			case "undefined": return e;
			case "object": return e;
			default: return "";
		}
	}
	function Ct(e) {
		var t = e.type;
		return (e = e.nodeName) && e.toLowerCase() === "input" && (t === "checkbox" || t === "radio");
	}
	function wt(e, t, n) {
		var r = Object.getOwnPropertyDescriptor(e.constructor.prototype, t);
		if (!e.hasOwnProperty(t) && r !== void 0 && typeof r.get == "function" && typeof r.set == "function") {
			var i = r.get, a = r.set;
			return Object.defineProperty(e, t, {
				configurable: !0,
				get: function() {
					return i.call(this);
				},
				set: function(e) {
					n = "" + e, a.call(this, e);
				}
			}), Object.defineProperty(e, t, { enumerable: r.enumerable }), {
				getValue: function() {
					return n;
				},
				setValue: function(e) {
					n = "" + e;
				},
				stopTracking: function() {
					e._valueTracker = null, delete e[t];
				}
			};
		}
	}
	function Tt(e) {
		if (!e._valueTracker) {
			var t = Ct(e) ? "checked" : "value";
			e._valueTracker = wt(e, t, "" + e[t]);
		}
	}
	function Et(e) {
		if (!e) return !1;
		var t = e._valueTracker;
		if (!t) return !0;
		var n = t.getValue(), r = "";
		return e && (r = Ct(e) ? e.checked ? "true" : "false" : e.value), e = r, e !== n && (t.setValue(e), !0);
	}
	function Dt(e) {
		if (e ||= typeof document < "u" ? document : void 0, e === void 0) return null;
		try {
			return e.activeElement || e.body;
		} catch {
			return e.body;
		}
	}
	var Ot = /[\n"\\]/g;
	function kt(e) {
		return e.replace(Ot, function(e) {
			return "\\" + e.charCodeAt(0).toString(16) + " ";
		});
	}
	function At(e, t, n, r, i, a, o, s) {
		e.name = "", o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" ? e.type = o : e.removeAttribute("type"), t == null ? o !== "submit" && o !== "reset" || e.removeAttribute("value") : o === "number" ? (t === 0 && e.value === "" || e.value != t) && (e.value = "" + St(t)) : e.value !== "" + St(t) && (e.value = "" + St(t)), t == null ? n == null ? r != null && e.removeAttribute("value") : Mt(e, o, St(n)) : Mt(e, o, St(t)), i == null && a != null && (e.defaultChecked = !!a), i != null && (e.checked = i && typeof i != "function" && typeof i != "symbol"), s != null && typeof s != "function" && typeof s != "symbol" && typeof s != "boolean" ? e.name = "" + St(s) : e.removeAttribute("name");
	}
	function jt(e, t, n, r, i, a, o, s) {
		if (a != null && typeof a != "function" && typeof a != "symbol" && typeof a != "boolean" && (e.type = a), t != null || n != null) {
			if (!(a !== "submit" && a !== "reset" || t != null)) {
				Tt(e);
				return;
			}
			n = n == null ? "" : "" + St(n), t = t == null ? n : "" + St(t), s || t === e.value || (e.value = t), e.defaultValue = t;
		}
		r ??= i, r = typeof r != "function" && typeof r != "symbol" && !!r, e.checked = s ? e.checked : !!r, e.defaultChecked = !!r, o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" && (e.name = o), Tt(e);
	}
	function Mt(e, t, n) {
		t === "number" && Dt(e.ownerDocument) === e || e.defaultValue === "" + n || (e.defaultValue = "" + n);
	}
	function Nt(e, t, n, r) {
		if (e = e.options, t) {
			t = {};
			for (var i = 0; i < n.length; i++) t["$" + n[i]] = !0;
			for (n = 0; n < e.length; n++) i = t.hasOwnProperty("$" + e[n].value), e[n].selected !== i && (e[n].selected = i), i && r && (e[n].defaultSelected = !0);
		} else {
			for (n = "" + St(n), t = null, i = 0; i < e.length; i++) {
				if (e[i].value === n) {
					e[i].selected = !0, r && (e[i].defaultSelected = !0);
					return;
				}
				t !== null || e[i].disabled || (t = e[i]);
			}
			t !== null && (t.selected = !0);
		}
	}
	function Pt(e, t, n) {
		if (t != null && (t = "" + St(t), t !== e.value && (e.value = t), n == null)) {
			e.defaultValue !== t && (e.defaultValue = t);
			return;
		}
		e.defaultValue = n == null ? "" : "" + St(n);
	}
	function Ft(e, t, n, r) {
		if (t == null) {
			if (r != null) {
				if (n != null) throw Error(s(92));
				if (F(r)) {
					if (1 < r.length) throw Error(s(93));
					r = r[0];
				}
				n = r;
			}
			n ??= "", t = n;
		}
		n = St(t), e.defaultValue = n, r = e.textContent, r === n && r !== "" && r !== null && (e.value = r), Tt(e);
	}
	function It(e, t) {
		if (t) {
			var n = e.firstChild;
			if (n && n === e.lastChild && n.nodeType === 3) {
				n.nodeValue = t;
				return;
			}
		}
		e.textContent = t;
	}
	var Lt = new Set("animationIterationCount aspectRatio borderImageOutset borderImageSlice borderImageWidth boxFlex boxFlexGroup boxOrdinalGroup columnCount columns flex flexGrow flexPositive flexShrink flexNegative flexOrder gridArea gridRow gridRowEnd gridRowSpan gridRowStart gridColumn gridColumnEnd gridColumnSpan gridColumnStart fontWeight lineClamp lineHeight opacity order orphans scale tabSize widows zIndex zoom fillOpacity floodOpacity stopOpacity strokeDasharray strokeDashoffset strokeMiterlimit strokeOpacity strokeWidth MozAnimationIterationCount MozBoxFlex MozBoxFlexGroup MozLineClamp msAnimationIterationCount msFlex msZoom msFlexGrow msFlexNegative msFlexOrder msFlexPositive msFlexShrink msGridColumn msGridColumnSpan msGridRow msGridRowSpan WebkitAnimationIterationCount WebkitBoxFlex WebKitBoxFlexGroup WebkitBoxOrdinalGroup WebkitColumnCount WebkitColumns WebkitFlex WebkitFlexGrow WebkitFlexPositive WebkitFlexShrink WebkitLineClamp".split(" "));
	function Rt(e, t, n) {
		var r = t.indexOf("--") === 0;
		n == null || typeof n == "boolean" || n === "" ? r ? e.setProperty(t, "") : t === "float" ? e.cssFloat = "" : e[t] = "" : r ? e.setProperty(t, n) : typeof n != "number" || n === 0 || Lt.has(t) ? t === "float" ? e.cssFloat = n : e[t] = ("" + n).trim() : e[t] = n + "px";
	}
	function zt(e, t, n) {
		if (t != null && typeof t != "object") throw Error(s(62));
		if (e = e.style, n != null) {
			for (var r in n) !n.hasOwnProperty(r) || t != null && t.hasOwnProperty(r) || (r.indexOf("--") === 0 ? e.setProperty(r, "") : r === "float" ? e.cssFloat = "" : e[r] = "");
			for (var i in t) r = t[i], t.hasOwnProperty(i) && n[i] !== r && Rt(e, i, r);
		} else for (var a in t) t.hasOwnProperty(a) && Rt(e, a, t[a]);
	}
	function Bt(e) {
		if (e.indexOf("-") === -1) return !1;
		switch (e) {
			case "annotation-xml":
			case "color-profile":
			case "font-face":
			case "font-face-src":
			case "font-face-uri":
			case "font-face-format":
			case "font-face-name":
			case "missing-glyph": return !1;
			default: return !0;
		}
	}
	var Vt = /* @__PURE__ */ new Map([
		["acceptCharset", "accept-charset"],
		["htmlFor", "for"],
		["httpEquiv", "http-equiv"],
		["crossOrigin", "crossorigin"],
		["accentHeight", "accent-height"],
		["alignmentBaseline", "alignment-baseline"],
		["arabicForm", "arabic-form"],
		["baselineShift", "baseline-shift"],
		["capHeight", "cap-height"],
		["clipPath", "clip-path"],
		["clipRule", "clip-rule"],
		["colorInterpolation", "color-interpolation"],
		["colorInterpolationFilters", "color-interpolation-filters"],
		["colorProfile", "color-profile"],
		["colorRendering", "color-rendering"],
		["dominantBaseline", "dominant-baseline"],
		["enableBackground", "enable-background"],
		["fillOpacity", "fill-opacity"],
		["fillRule", "fill-rule"],
		["floodColor", "flood-color"],
		["floodOpacity", "flood-opacity"],
		["fontFamily", "font-family"],
		["fontSize", "font-size"],
		["fontSizeAdjust", "font-size-adjust"],
		["fontStretch", "font-stretch"],
		["fontStyle", "font-style"],
		["fontVariant", "font-variant"],
		["fontWeight", "font-weight"],
		["glyphName", "glyph-name"],
		["glyphOrientationHorizontal", "glyph-orientation-horizontal"],
		["glyphOrientationVertical", "glyph-orientation-vertical"],
		["horizAdvX", "horiz-adv-x"],
		["horizOriginX", "horiz-origin-x"],
		["imageRendering", "image-rendering"],
		["letterSpacing", "letter-spacing"],
		["lightingColor", "lighting-color"],
		["markerEnd", "marker-end"],
		["markerMid", "marker-mid"],
		["markerStart", "marker-start"],
		["overlinePosition", "overline-position"],
		["overlineThickness", "overline-thickness"],
		["paintOrder", "paint-order"],
		["panose-1", "panose-1"],
		["pointerEvents", "pointer-events"],
		["renderingIntent", "rendering-intent"],
		["shapeRendering", "shape-rendering"],
		["stopColor", "stop-color"],
		["stopOpacity", "stop-opacity"],
		["strikethroughPosition", "strikethrough-position"],
		["strikethroughThickness", "strikethrough-thickness"],
		["strokeDasharray", "stroke-dasharray"],
		["strokeDashoffset", "stroke-dashoffset"],
		["strokeLinecap", "stroke-linecap"],
		["strokeLinejoin", "stroke-linejoin"],
		["strokeMiterlimit", "stroke-miterlimit"],
		["strokeOpacity", "stroke-opacity"],
		["strokeWidth", "stroke-width"],
		["textAnchor", "text-anchor"],
		["textDecoration", "text-decoration"],
		["textRendering", "text-rendering"],
		["transformOrigin", "transform-origin"],
		["underlinePosition", "underline-position"],
		["underlineThickness", "underline-thickness"],
		["unicodeBidi", "unicode-bidi"],
		["unicodeRange", "unicode-range"],
		["unitsPerEm", "units-per-em"],
		["vAlphabetic", "v-alphabetic"],
		["vHanging", "v-hanging"],
		["vIdeographic", "v-ideographic"],
		["vMathematical", "v-mathematical"],
		["vectorEffect", "vector-effect"],
		["vertAdvY", "vert-adv-y"],
		["vertOriginX", "vert-origin-x"],
		["vertOriginY", "vert-origin-y"],
		["wordSpacing", "word-spacing"],
		["writingMode", "writing-mode"],
		["xmlnsXlink", "xmlns:xlink"],
		["xHeight", "x-height"]
	]), Ht = /^[\u0000-\u001F ]*j[\r\n\t]*a[\r\n\t]*v[\r\n\t]*a[\r\n\t]*s[\r\n\t]*c[\r\n\t]*r[\r\n\t]*i[\r\n\t]*p[\r\n\t]*t[\r\n\t]*:/i;
	function Ut(e) {
		return Ht.test("" + e) ? "javascript:throw new Error('React has blocked a javascript: URL as a security precaution.')" : e;
	}
	function Wt() {}
	var Gt = null;
	function Kt(e) {
		return e = e.target || e.srcElement || window, e.correspondingUseElement && (e = e.correspondingUseElement), e.nodeType === 3 ? e.parentNode : e;
	}
	var qt = null, Jt = null;
	function Yt(e) {
		var t = st(e);
		if (t && (e = t.stateNode)) {
			var n = e[Qe] || null;
			a: switch (e = t.stateNode, t.type) {
				case "input":
					if (At(e, n.value, n.defaultValue, n.defaultValue, n.checked, n.defaultChecked, n.type, n.name), t = n.name, n.type === "radio" && t != null) {
						for (n = e; n.parentNode;) n = n.parentNode;
						for (n = n.querySelectorAll("input[name=\"" + kt("" + t) + "\"][type=\"radio\"]"), t = 0; t < n.length; t++) {
							var r = n[t];
							if (r !== e && r.form === e.form) {
								var i = r[Qe] || null;
								if (!i) throw Error(s(90));
								At(r, i.value, i.defaultValue, i.defaultValue, i.checked, i.defaultChecked, i.type, i.name);
							}
						}
						for (t = 0; t < n.length; t++) r = n[t], r.form === e.form && Et(r);
					}
					break a;
				case "textarea":
					Pt(e, n.value, n.defaultValue);
					break a;
				case "select": t = n.value, t != null && Nt(e, !!n.multiple, t, !1);
			}
		}
	}
	var Xt = !1;
	function Zt(e, t, n) {
		if (Xt) return e(t, n);
		Xt = !0;
		try {
			return e(t);
		} finally {
			if (Xt = !1, (qt !== null || Jt !== null) && (vu(), qt && (t = qt, e = Jt, Jt = qt = null, Yt(t), e))) for (t = 0; t < e.length; t++) Yt(e[t]);
		}
	}
	function Qt(e, t) {
		var n = e.stateNode;
		if (n === null) return null;
		var r = n[Qe] || null;
		if (r === null) return null;
		n = r[t];
		a: switch (t) {
			case "onClick":
			case "onClickCapture":
			case "onDoubleClick":
			case "onDoubleClickCapture":
			case "onMouseDown":
			case "onMouseDownCapture":
			case "onMouseMove":
			case "onMouseMoveCapture":
			case "onMouseUp":
			case "onMouseUpCapture":
			case "onMouseEnter":
				(r = !r.disabled) || (e = e.type, r = e !== "button" && e !== "input" && e !== "select" && e !== "textarea"), e = !r;
				break a;
			default: e = !1;
		}
		if (e) return null;
		if (n && typeof n != "function") throw Error(s(231, t, typeof n));
		return n;
	}
	var $t = !(typeof window > "u" || window.document === void 0 || window.document.createElement === void 0), en = !1;
	if ($t) try {
		var tn = {};
		Object.defineProperty(tn, "passive", { get: function() {
			en = !0;
		} }), window.addEventListener("test", tn, tn), window.removeEventListener("test", tn, tn);
	} catch {
		en = !1;
	}
	var nn = null, rn = null, an = null;
	function on() {
		if (an) return an;
		var e, t = rn, n = t.length, r, i = "value" in nn ? nn.value : nn.textContent, a = i.length;
		for (e = 0; e < n && t[e] === i[e]; e++);
		var o = n - e;
		for (r = 1; r <= o && t[n - r] === i[a - r]; r++);
		return an = i.slice(e, 1 < r ? 1 - r : void 0);
	}
	function sn(e) {
		var t = e.keyCode;
		return "charCode" in e ? (e = e.charCode, e === 0 && t === 13 && (e = 13)) : e = t, e === 10 && (e = 13), 32 <= e || e === 13 ? e : 0;
	}
	function cn() {
		return !0;
	}
	function ln() {
		return !1;
	}
	function un(e) {
		function t(t, n, r, i, a) {
			for (var o in this._reactName = t, this._targetInst = r, this.type = n, this.nativeEvent = i, this.target = a, this.currentTarget = null, e) e.hasOwnProperty(o) && (t = e[o], this[o] = t ? t(i) : i[o]);
			return this.isDefaultPrevented = (i.defaultPrevented == null ? !1 === i.returnValue : i.defaultPrevented) ? cn : ln, this.isPropagationStopped = ln, this;
		}
		return h(t.prototype, {
			preventDefault: function() {
				this.defaultPrevented = !0;
				var e = this.nativeEvent;
				e && (e.preventDefault ? e.preventDefault() : typeof e.returnValue != "unknown" && (e.returnValue = !1), this.isDefaultPrevented = cn);
			},
			stopPropagation: function() {
				var e = this.nativeEvent;
				e && (e.stopPropagation ? e.stopPropagation() : typeof e.cancelBubble != "unknown" && (e.cancelBubble = !0), this.isPropagationStopped = cn);
			},
			persist: function() {},
			isPersistent: cn
		}), t;
	}
	var dn = {
		eventPhase: 0,
		bubbles: 0,
		cancelable: 0,
		timeStamp: function(e) {
			return e.timeStamp || Date.now();
		},
		defaultPrevented: 0,
		isTrusted: 0
	}, fn = un(dn), pn = h({}, dn, {
		view: 0,
		detail: 0
	}), mn = un(pn), hn, gn, _n, vn = h({}, pn, {
		screenX: 0,
		screenY: 0,
		clientX: 0,
		clientY: 0,
		pageX: 0,
		pageY: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		getModifierState: kn,
		button: 0,
		buttons: 0,
		relatedTarget: function(e) {
			return e.relatedTarget === void 0 ? e.fromElement === e.srcElement ? e.toElement : e.fromElement : e.relatedTarget;
		},
		movementX: function(e) {
			return "movementX" in e ? e.movementX : (e !== _n && (_n && e.type === "mousemove" ? (hn = e.screenX - _n.screenX, gn = e.screenY - _n.screenY) : gn = hn = 0, _n = e), hn);
		},
		movementY: function(e) {
			return "movementY" in e ? e.movementY : gn;
		}
	}), yn = un(vn), bn = un(h({}, vn, { dataTransfer: 0 })), xn = un(h({}, pn, { relatedTarget: 0 })), Sn = un(h({}, dn, {
		animationName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), Cn = un(h({}, dn, { clipboardData: function(e) {
		return "clipboardData" in e ? e.clipboardData : window.clipboardData;
	} })), wn = un(h({}, dn, { data: 0 })), Tn = {
		Esc: "Escape",
		Spacebar: " ",
		Left: "ArrowLeft",
		Up: "ArrowUp",
		Right: "ArrowRight",
		Down: "ArrowDown",
		Del: "Delete",
		Win: "OS",
		Menu: "ContextMenu",
		Apps: "ContextMenu",
		Scroll: "ScrollLock",
		MozPrintableKey: "Unidentified"
	}, En = {
		8: "Backspace",
		9: "Tab",
		12: "Clear",
		13: "Enter",
		16: "Shift",
		17: "Control",
		18: "Alt",
		19: "Pause",
		20: "CapsLock",
		27: "Escape",
		32: " ",
		33: "PageUp",
		34: "PageDown",
		35: "End",
		36: "Home",
		37: "ArrowLeft",
		38: "ArrowUp",
		39: "ArrowRight",
		40: "ArrowDown",
		45: "Insert",
		46: "Delete",
		112: "F1",
		113: "F2",
		114: "F3",
		115: "F4",
		116: "F5",
		117: "F6",
		118: "F7",
		119: "F8",
		120: "F9",
		121: "F10",
		122: "F11",
		123: "F12",
		144: "NumLock",
		145: "ScrollLock",
		224: "Meta"
	}, Dn = {
		Alt: "altKey",
		Control: "ctrlKey",
		Meta: "metaKey",
		Shift: "shiftKey"
	};
	function On(e) {
		var t = this.nativeEvent;
		return t.getModifierState ? t.getModifierState(e) : (e = Dn[e]) ? !!t[e] : !1;
	}
	function kn() {
		return On;
	}
	var An = un(h({}, pn, {
		key: function(e) {
			if (e.key) {
				var t = Tn[e.key] || e.key;
				if (t !== "Unidentified") return t;
			}
			return e.type === "keypress" ? (e = sn(e), e === 13 ? "Enter" : String.fromCharCode(e)) : e.type === "keydown" || e.type === "keyup" ? En[e.keyCode] || "Unidentified" : "";
		},
		code: 0,
		location: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		repeat: 0,
		locale: 0,
		getModifierState: kn,
		charCode: function(e) {
			return e.type === "keypress" ? sn(e) : 0;
		},
		keyCode: function(e) {
			return e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		},
		which: function(e) {
			return e.type === "keypress" ? sn(e) : e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		}
	})), jn = un(h({}, vn, {
		pointerId: 0,
		width: 0,
		height: 0,
		pressure: 0,
		tangentialPressure: 0,
		tiltX: 0,
		tiltY: 0,
		twist: 0,
		pointerType: 0,
		isPrimary: 0
	})), Mn = un(h({}, pn, {
		touches: 0,
		targetTouches: 0,
		changedTouches: 0,
		altKey: 0,
		metaKey: 0,
		ctrlKey: 0,
		shiftKey: 0,
		getModifierState: kn
	})), Nn = un(h({}, dn, {
		propertyName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), Pn = un(h({}, vn, {
		deltaX: function(e) {
			return "deltaX" in e ? e.deltaX : "wheelDeltaX" in e ? -e.wheelDeltaX : 0;
		},
		deltaY: function(e) {
			return "deltaY" in e ? e.deltaY : "wheelDeltaY" in e ? -e.wheelDeltaY : "wheelDelta" in e ? -e.wheelDelta : 0;
		},
		deltaZ: 0,
		deltaMode: 0
	})), Fn = un(h({}, dn, {
		newState: 0,
		oldState: 0
	})), In = [
		9,
		13,
		27,
		32
	], Ln = $t && "CompositionEvent" in window, Rn = null;
	$t && "documentMode" in document && (Rn = document.documentMode);
	var zn = $t && "TextEvent" in window && !Rn, Bn = $t && (!Ln || Rn && 8 < Rn && 11 >= Rn), Vn = " ", Hn = !1;
	function Un(e, t) {
		switch (e) {
			case "keyup": return In.indexOf(t.keyCode) !== -1;
			case "keydown": return t.keyCode !== 229;
			case "keypress":
			case "mousedown":
			case "focusout": return !0;
			default: return !1;
		}
	}
	function Wn(e) {
		return e = e.detail, typeof e == "object" && "data" in e ? e.data : null;
	}
	var Gn = !1;
	function Kn(e, t) {
		switch (e) {
			case "compositionend": return Wn(t);
			case "keypress": return t.which === 32 ? (Hn = !0, Vn) : null;
			case "textInput": return e = t.data, e === Vn && Hn ? null : e;
			default: return null;
		}
	}
	function qn(e, t) {
		if (Gn) return e === "compositionend" || !Ln && Un(e, t) ? (e = on(), an = rn = nn = null, Gn = !1, e) : null;
		switch (e) {
			case "paste": return null;
			case "keypress":
				if (!(t.ctrlKey || t.altKey || t.metaKey) || t.ctrlKey && t.altKey) {
					if (t.char && 1 < t.char.length) return t.char;
					if (t.which) return String.fromCharCode(t.which);
				}
				return null;
			case "compositionend": return Bn && t.locale !== "ko" ? null : t.data;
			default: return null;
		}
	}
	var Jn = {
		color: !0,
		date: !0,
		datetime: !0,
		"datetime-local": !0,
		email: !0,
		month: !0,
		number: !0,
		password: !0,
		range: !0,
		search: !0,
		tel: !0,
		text: !0,
		time: !0,
		url: !0,
		week: !0
	};
	function Yn(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t === "input" ? !!Jn[e.type] : t === "textarea";
	}
	function Xn(e, t, n, r) {
		qt ? Jt ? Jt.push(r) : Jt = [r] : qt = r, t = Td(t, "onChange"), 0 < t.length && (n = new fn("onChange", "change", null, n, r), e.push({
			event: n,
			listeners: t
		}));
	}
	var Zn = null, Qn = null;
	function $n(e) {
		vd(e, 0);
	}
	function er(e) {
		if (Et(ct(e))) return e;
	}
	function tr(e, t) {
		if (e === "change") return t;
	}
	var J = !1;
	if ($t) {
		var nr;
		if ($t) {
			var rr = "oninput" in document;
			if (!rr) {
				var ir = document.createElement("div");
				ir.setAttribute("oninput", "return;"), rr = typeof ir.oninput == "function";
			}
			nr = rr;
		} else nr = !1;
		J = nr && (!document.documentMode || 9 < document.documentMode);
	}
	function ar() {
		Zn && (Zn.detachEvent("onpropertychange", or), Qn = Zn = null);
	}
	function or(e) {
		if (e.propertyName === "value" && er(Qn)) {
			var t = [];
			Xn(t, Qn, e, Kt(e)), Zt($n, t);
		}
	}
	function sr(e, t, n) {
		e === "focusin" ? (ar(), Zn = t, Qn = n, Zn.attachEvent("onpropertychange", or)) : e === "focusout" && ar();
	}
	function cr(e) {
		if (e === "selectionchange" || e === "keyup" || e === "keydown") return er(Qn);
	}
	function lr(e, t) {
		if (e === "click") return er(t);
	}
	function ur(e, t) {
		if (e === "input" || e === "change") return er(t);
	}
	function dr(e, t) {
		return e === t && (e !== 0 || 1 / e == 1 / t) || e !== e && t !== t;
	}
	var fr = typeof Object.is == "function" ? Object.is : dr;
	function pr(e, t) {
		if (fr(e, t)) return !0;
		if (typeof e != "object" || !e || typeof t != "object" || !t) return !1;
		var n = Object.keys(e), r = Object.keys(t);
		if (n.length !== r.length) return !1;
		for (r = 0; r < n.length; r++) {
			var i = n[r];
			if (!de.call(t, i) || !fr(e[i], t[i])) return !1;
		}
		return !0;
	}
	function mr(e) {
		for (; e && e.firstChild;) e = e.firstChild;
		return e;
	}
	function hr(e, t) {
		var n = mr(e);
		e = 0;
		for (var r; n;) {
			if (n.nodeType === 3) {
				if (r = e + n.textContent.length, e <= t && r >= t) return {
					node: n,
					offset: t - e
				};
				e = r;
			}
			a: {
				for (; n;) {
					if (n.nextSibling) {
						n = n.nextSibling;
						break a;
					}
					n = n.parentNode;
				}
				n = void 0;
			}
			n = mr(n);
		}
	}
	function gr(e, t) {
		return e && t ? e === t ? !0 : e && e.nodeType === 3 ? !1 : t && t.nodeType === 3 ? gr(e, t.parentNode) : "contains" in e ? e.contains(t) : e.compareDocumentPosition ? !!(e.compareDocumentPosition(t) & 16) : !1 : !1;
	}
	function _r(e) {
		e = e != null && e.ownerDocument != null && e.ownerDocument.defaultView != null ? e.ownerDocument.defaultView : window;
		for (var t = Dt(e.document); t instanceof e.HTMLIFrameElement;) {
			try {
				var n = typeof t.contentWindow.location.href == "string";
			} catch {
				n = !1;
			}
			if (n) e = t.contentWindow;
			else break;
			t = Dt(e.document);
		}
		return t;
	}
	function vr(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t && (t === "input" && (e.type === "text" || e.type === "search" || e.type === "tel" || e.type === "url" || e.type === "password") || t === "textarea" || e.contentEditable === "true");
	}
	var yr = $t && "documentMode" in document && 11 >= document.documentMode, br = null, xr = null, Sr = null, Cr = !1;
	function wr(e, t, n) {
		var r = n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
		Cr || br == null || br !== Dt(r) || (r = br, "selectionStart" in r && vr(r) ? r = {
			start: r.selectionStart,
			end: r.selectionEnd
		} : (r = (r.ownerDocument && r.ownerDocument.defaultView || window).getSelection(), r = {
			anchorNode: r.anchorNode,
			anchorOffset: r.anchorOffset,
			focusNode: r.focusNode,
			focusOffset: r.focusOffset
		}), Sr && pr(Sr, r) || (Sr = r, r = Td(xr, "onSelect"), 0 < r.length && (t = new fn("onSelect", "select", null, t, n), e.push({
			event: t,
			listeners: r
		}), t.target = br)));
	}
	function Tr(e, t) {
		var n = {};
		return n[e.toLowerCase()] = t.toLowerCase(), n["Webkit" + e] = "webkit" + t, n["Moz" + e] = "moz" + t, n;
	}
	var Er = {
		animationend: Tr("Animation", "AnimationEnd"),
		animationiteration: Tr("Animation", "AnimationIteration"),
		animationstart: Tr("Animation", "AnimationStart"),
		transitionrun: Tr("Transition", "TransitionRun"),
		transitionstart: Tr("Transition", "TransitionStart"),
		transitioncancel: Tr("Transition", "TransitionCancel"),
		transitionend: Tr("Transition", "TransitionEnd")
	}, Dr = {}, Or = {};
	$t && (Or = document.createElement("div").style, "AnimationEvent" in window || (delete Er.animationend.animation, delete Er.animationiteration.animation, delete Er.animationstart.animation), "TransitionEvent" in window || delete Er.transitionend.transition);
	function kr(e) {
		if (Dr[e]) return Dr[e];
		if (!Er[e]) return e;
		var t = Er[e], n;
		for (n in t) if (t.hasOwnProperty(n) && n in Or) return Dr[e] = t[n];
		return e;
	}
	var Ar = kr("animationend"), jr = kr("animationiteration"), Mr = kr("animationstart"), Nr = kr("transitionrun"), Pr = kr("transitionstart"), Fr = kr("transitioncancel"), Ir = kr("transitionend"), Lr = /* @__PURE__ */ new Map(), Rr = "abort auxClick beforeToggle cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
	Rr.push("scrollEnd");
	function zr(e, t) {
		Lr.set(e, t), pt(t, [e]);
	}
	var Br = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	}, Vr = [], Hr = 0, Ur = 0;
	function Wr() {
		for (var e = Hr, t = Ur = Hr = 0; t < e;) {
			var n = Vr[t];
			Vr[t++] = null;
			var r = Vr[t];
			Vr[t++] = null;
			var i = Vr[t];
			Vr[t++] = null;
			var a = Vr[t];
			if (Vr[t++] = null, r !== null && i !== null) {
				var o = r.pending;
				o === null ? i.next = i : (i.next = o.next, o.next = i), r.pending = i;
			}
			a !== 0 && Jr(n, i, a);
		}
	}
	function Gr(e, t, n, r) {
		Vr[Hr++] = e, Vr[Hr++] = t, Vr[Hr++] = n, Vr[Hr++] = r, Ur |= r, e.lanes |= r, e = e.alternate, e !== null && (e.lanes |= r);
	}
	function Kr(e, t, n, r) {
		return Gr(e, t, n, r), Yr(e);
	}
	function qr(e, t) {
		return Gr(e, null, null, t), Yr(e);
	}
	function Jr(e, t, n) {
		e.lanes |= n;
		var r = e.alternate;
		r !== null && (r.lanes |= n);
		for (var i = !1, a = e.return; a !== null;) a.childLanes |= n, r = a.alternate, r !== null && (r.childLanes |= n), a.tag === 22 && (e = a.stateNode, e === null || e._visibility & 1 || (i = !0)), e = a, a = a.return;
		return e.tag === 3 ? (a = e.stateNode, i && t !== null && (i = 31 - Oe(n), e = a.hiddenUpdates, r = e[i], r === null ? e[i] = [t] : r.push(t), t.lane = n | 536870912), a) : null;
	}
	function Yr(e) {
		if (50 < lu) throw lu = 0, uu = null, Error(s(185));
		for (var t = e.return; t !== null;) e = t, t = e.return;
		return e.tag === 3 ? e.stateNode : null;
	}
	var Xr = {};
	function Zr(e, t, n, r) {
		this.tag = e, this.key = n, this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null, this.index = 0, this.refCleanup = this.ref = null, this.pendingProps = t, this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null, this.mode = r, this.subtreeFlags = this.flags = 0, this.deletions = null, this.childLanes = this.lanes = 0, this.alternate = null;
	}
	function Qr(e, t, n, r) {
		return new Zr(e, t, n, r);
	}
	function $r(e) {
		return e = e.prototype, !(!e || !e.isReactComponent);
	}
	function ei(e, t) {
		var n = e.alternate;
		return n === null ? (n = Qr(e.tag, t, e.key, e.mode), n.elementType = e.elementType, n.type = e.type, n.stateNode = e.stateNode, n.alternate = e, e.alternate = n) : (n.pendingProps = t, n.type = e.type, n.flags = 0, n.subtreeFlags = 0, n.deletions = null), n.flags = e.flags & 65011712, n.childLanes = e.childLanes, n.lanes = e.lanes, n.child = e.child, n.memoizedProps = e.memoizedProps, n.memoizedState = e.memoizedState, n.updateQueue = e.updateQueue, t = e.dependencies, n.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}, n.sibling = e.sibling, n.index = e.index, n.ref = e.ref, n.refCleanup = e.refCleanup, n;
	}
	function ti(e, t) {
		e.flags &= 65011714;
		var n = e.alternate;
		return n === null ? (e.childLanes = 0, e.lanes = t, e.child = null, e.subtreeFlags = 0, e.memoizedProps = null, e.memoizedState = null, e.updateQueue = null, e.dependencies = null, e.stateNode = null) : (e.childLanes = n.childLanes, e.lanes = n.lanes, e.child = n.child, e.subtreeFlags = 0, e.deletions = null, e.memoizedProps = n.memoizedProps, e.memoizedState = n.memoizedState, e.updateQueue = n.updateQueue, e.type = n.type, t = n.dependencies, e.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}), e;
	}
	function ni(e, t, n, r, i, a) {
		var o = 0;
		if (r = e, typeof e == "function") $r(e) && (o = 1);
		else if (typeof e == "string") o = Uf(e, n, ee.current) ? 26 : e === "html" || e === "head" || e === "body" ? 27 : 5;
		else a: switch (e) {
			case k: return e = Qr(31, n, t, i), e.elementType = k, e.lanes = a, e;
			case y: return ri(n.children, i, a, t);
			case b:
				o = 8, i |= 24;
				break;
			case x: return e = Qr(12, n, t, i | 2), e.elementType = x, e.lanes = a, e;
			case T: return e = Qr(13, n, t, i), e.elementType = T, e.lanes = a, e;
			case E: return e = Qr(19, n, t, i), e.elementType = E, e.lanes = a, e;
			default:
				if (typeof e == "object" && e) switch (e.$$typeof) {
					case C:
						o = 10;
						break a;
					case S:
						o = 9;
						break a;
					case w:
						o = 11;
						break a;
					case D:
						o = 14;
						break a;
					case O:
						o = 16, r = null;
						break a;
				}
				o = 29, n = Error(s(130, e === null ? "null" : typeof e, "")), r = null;
		}
		return t = Qr(o, n, t, i), t.elementType = e, t.type = r, t.lanes = a, t;
	}
	function ri(e, t, n, r) {
		return e = Qr(7, e, r, t), e.lanes = n, e;
	}
	function ii(e, t, n) {
		return e = Qr(6, e, null, t), e.lanes = n, e;
	}
	function ai(e) {
		var t = Qr(18, null, null, 0);
		return t.stateNode = e, t;
	}
	function oi(e, t, n) {
		return t = Qr(4, e.children === null ? [] : e.children, e.key, t), t.lanes = n, t.stateNode = {
			containerInfo: e.containerInfo,
			pendingChildren: null,
			implementation: e.implementation
		}, t;
	}
	var si = /* @__PURE__ */ new WeakMap();
	function ci(e, t) {
		if (typeof e == "object" && e) {
			var n = si.get(e);
			return n === void 0 ? (t = {
				value: e,
				source: t,
				stack: ue(t)
			}, si.set(e, t), t) : n;
		}
		return {
			value: e,
			source: t,
			stack: ue(t)
		};
	}
	var li = [], ui = 0, di = null, fi = 0, pi = [], mi = 0, hi = null, gi = 1, _i = "";
	function vi(e, t) {
		li[ui++] = fi, li[ui++] = di, di = e, fi = t;
	}
	function yi(e, t, n) {
		pi[mi++] = gi, pi[mi++] = _i, pi[mi++] = hi, hi = e;
		var r = gi;
		e = _i;
		var i = 32 - Oe(r) - 1;
		r &= ~(1 << i), n += 1;
		var a = 32 - Oe(t) + i;
		if (30 < a) {
			var o = i - i % 5;
			a = (r & (1 << o) - 1).toString(32), r >>= o, i -= o, gi = 1 << 32 - Oe(t) + i | n << i | r, _i = a + e;
		} else gi = 1 << a | n << i | r, _i = e;
	}
	function bi(e) {
		e.return !== null && (vi(e, 1), yi(e, 1, 0));
	}
	function xi(e) {
		for (; e === di;) di = li[--ui], li[ui] = null, fi = li[--ui], li[ui] = null;
		for (; e === hi;) hi = pi[--mi], pi[mi] = null, _i = pi[--mi], pi[mi] = null, gi = pi[--mi], pi[mi] = null;
	}
	function Si(e, t) {
		pi[mi++] = gi, pi[mi++] = _i, pi[mi++] = hi, gi = t.id, _i = t.overflow, hi = e;
	}
	var Ci = null, wi = null, Ti = !1, Ei = null, Di = !1, Oi = Error(s(519));
	function ki(e) {
		throw Fi(ci(Error(s(418, 1 < arguments.length && arguments[1] !== void 0 && arguments[1] ? "text" : "HTML", "")), e)), Oi;
	}
	function Ai(e) {
		var t = e.stateNode, n = e.type, r = e.memoizedProps;
		switch (t[Ze] = e, t[Qe] = r, n) {
			case "dialog":
				$("cancel", t), $("close", t);
				break;
			case "iframe":
			case "object":
			case "embed":
				$("load", t);
				break;
			case "video":
			case "audio":
				for (n = 0; n < gd.length; n++) $(gd[n], t);
				break;
			case "source":
				$("error", t);
				break;
			case "img":
			case "image":
			case "link":
				$("error", t), $("load", t);
				break;
			case "details":
				$("toggle", t);
				break;
			case "input":
				$("invalid", t), jt(t, r.value, r.defaultValue, r.checked, r.defaultChecked, r.type, r.name, !0);
				break;
			case "select":
				$("invalid", t);
				break;
			case "textarea": $("invalid", t), Ft(t, r.value, r.defaultValue, r.children);
		}
		n = r.children, typeof n != "string" && typeof n != "number" && typeof n != "bigint" || t.textContent === "" + n || !0 === r.suppressHydrationWarning || jd(t.textContent, n) ? (r.popover != null && ($("beforetoggle", t), $("toggle", t)), r.onScroll != null && $("scroll", t), r.onScrollEnd != null && $("scrollend", t), r.onClick != null && (t.onclick = Wt), t = !0) : t = !1, t || ki(e, !0);
	}
	function ji(e) {
		for (Ci = e.return; Ci;) switch (Ci.tag) {
			case 5:
			case 31:
			case 13:
				Di = !1;
				return;
			case 27:
			case 3:
				Di = !0;
				return;
			default: Ci = Ci.return;
		}
	}
	function Mi(e) {
		if (e !== Ci) return !1;
		if (!Ti) return ji(e), Ti = !0, !1;
		var t = e.tag, n;
		if ((n = t !== 3 && t !== 27) && ((n = t === 5) && (n = e.type, n = n === "form" || n === "button" || Ud(e.type, e.memoizedProps)), n = !n), n && wi && ki(e), ji(e), t === 13) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			wi = uf(e);
		} else if (t === 31) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			wi = uf(e);
		} else t === 27 ? (t = wi, Zd(e.type) ? (e = lf, lf = null, wi = e) : wi = t) : wi = Ci ? cf(e.stateNode.nextSibling) : null;
		return !0;
	}
	function Ni() {
		wi = Ci = null, Ti = !1;
	}
	function Pi() {
		var e = Ei;
		return e !== null && (Yl === null ? Yl = e : Yl.push.apply(Yl, e), Ei = null), e;
	}
	function Fi(e) {
		Ei === null ? Ei = [e] : Ei.push(e);
	}
	var Ii = V(null), Li = null, Ri = null;
	function zi(e, t, n) {
		U(Ii, t._currentValue), t._currentValue = n;
	}
	function Bi(e) {
		e._currentValue = Ii.current, H(Ii);
	}
	function Vi(e, t, n) {
		for (; e !== null;) {
			var r = e.alternate;
			if ((e.childLanes & t) === t ? r !== null && (r.childLanes & t) !== t && (r.childLanes |= t) : (e.childLanes |= t, r !== null && (r.childLanes |= t)), e === n) break;
			e = e.return;
		}
	}
	function Hi(e, t, n, r) {
		var i = e.child;
		for (i !== null && (i.return = e); i !== null;) {
			var a = i.dependencies;
			if (a !== null) {
				var o = i.child;
				a = a.firstContext;
				a: for (; a !== null;) {
					var c = a;
					a = i;
					for (var l = 0; l < t.length; l++) if (c.context === t[l]) {
						a.lanes |= n, c = a.alternate, c !== null && (c.lanes |= n), Vi(a.return, n, e), r || (o = null);
						break a;
					}
					a = c.next;
				}
			} else if (i.tag === 18) {
				if (o = i.return, o === null) throw Error(s(341));
				o.lanes |= n, a = o.alternate, a !== null && (a.lanes |= n), Vi(o, n, e), o = null;
			} else o = i.child;
			if (o !== null) o.return = i;
			else for (o = i; o !== null;) {
				if (o === e) {
					o = null;
					break;
				}
				if (i = o.sibling, i !== null) {
					i.return = o.return, o = i;
					break;
				}
				o = o.return;
			}
			i = o;
		}
	}
	function Ui(e, t, n, r) {
		e = null;
		for (var i = t, a = !1; i !== null;) {
			if (!a) {
				if (i.flags & 524288) a = !0;
				else if (i.flags & 262144) break;
			}
			if (i.tag === 10) {
				var o = i.alternate;
				if (o === null) throw Error(s(387));
				if (o = o.memoizedProps, o !== null) {
					var c = i.type;
					fr(i.pendingProps.value, o.value) || (e === null ? e = [c] : e.push(c));
				}
			} else if (i === G.current) {
				if (o = i.alternate, o === null) throw Error(s(387));
				o.memoizedState.memoizedState !== i.memoizedState.memoizedState && (e === null ? e = [Qf] : e.push(Qf));
			}
			i = i.return;
		}
		e !== null && Hi(t, e, n, r), t.flags |= 262144;
	}
	function Wi(e) {
		for (e = e.firstContext; e !== null;) {
			if (!fr(e.context._currentValue, e.memoizedValue)) return !0;
			e = e.next;
		}
		return !1;
	}
	function Gi(e) {
		Li = e, Ri = null, e = e.dependencies, e !== null && (e.firstContext = null);
	}
	function Ki(e) {
		return Ji(Li, e);
	}
	function qi(e, t) {
		return Li === null && Gi(e), Ji(e, t);
	}
	function Ji(e, t) {
		var n = t._currentValue;
		if (t = {
			context: t,
			memoizedValue: n,
			next: null
		}, Ri === null) {
			if (e === null) throw Error(s(308));
			Ri = t, e.dependencies = {
				lanes: 0,
				firstContext: t
			}, e.flags |= 524288;
		} else Ri = Ri.next = t;
		return n;
	}
	var Yi = typeof AbortController < "u" ? AbortController : function() {
		var e = [], t = this.signal = {
			aborted: !1,
			addEventListener: function(t, n) {
				e.push(n);
			}
		};
		this.abort = function() {
			t.aborted = !0, e.forEach(function(e) {
				return e();
			});
		};
	}, Xi = t.unstable_scheduleCallback, Zi = t.unstable_NormalPriority, Qi = {
		$$typeof: C,
		Consumer: null,
		Provider: null,
		_currentValue: null,
		_currentValue2: null,
		_threadCount: 0
	};
	function $i() {
		return {
			controller: new Yi(),
			data: /* @__PURE__ */ new Map(),
			refCount: 0
		};
	}
	function ea(e) {
		e.refCount--, e.refCount === 0 && Xi(Zi, function() {
			e.controller.abort();
		});
	}
	var ta = null, na = 0, ra = 0, ia = null;
	function aa(e, t) {
		if (ta === null) {
			var n = ta = [];
			na = 0, ra = ud(), ia = {
				status: "pending",
				value: void 0,
				then: function(e) {
					n.push(e);
				}
			};
		}
		return na++, t.then(oa, oa), t;
	}
	function oa() {
		if (--na === 0 && ta !== null) {
			ia !== null && (ia.status = "fulfilled");
			var e = ta;
			ta = null, ra = 0, ia = null;
			for (var t = 0; t < e.length; t++) (0, e[t])();
		}
	}
	function sa(e, t) {
		var n = [], r = {
			status: "pending",
			value: null,
			reason: null,
			then: function(e) {
				n.push(e);
			}
		};
		return e.then(function() {
			r.status = "fulfilled", r.value = t;
			for (var e = 0; e < n.length; e++) (0, n[e])(t);
		}, function(e) {
			for (r.status = "rejected", r.reason = e, e = 0; e < n.length; e++) (0, n[e])(void 0);
		}), r;
	}
	var ca = I.S;
	I.S = function(e, t) {
		Ql = ge(), typeof t == "object" && t && typeof t.then == "function" && aa(e, t), ca !== null && ca(e, t);
	};
	var la = V(null);
	function ua() {
		var e = la.current;
		return e === null ? Fl.pooledCache : e;
	}
	function da(e, t) {
		t === null ? U(la, la.current) : U(la, t.pool);
	}
	function fa() {
		var e = ua();
		return e === null ? null : {
			parent: Qi._currentValue,
			pool: e
		};
	}
	var pa = Error(s(460)), ma = Error(s(474)), ha = Error(s(542)), ga = { then: function() {} };
	function _a(e) {
		return e = e.status, e === "fulfilled" || e === "rejected";
	}
	function va(e, t, n) {
		switch (n = e[n], n === void 0 ? e.push(t) : n !== t && (t.then(Wt, Wt), t = n), t.status) {
			case "fulfilled": return t.value;
			case "rejected": throw e = t.reason, Sa(e), e;
			default:
				if (typeof t.status == "string") t.then(Wt, Wt);
				else {
					if (e = Fl, e !== null && 100 < e.shellSuspendCounter) throw Error(s(482));
					e = t, e.status = "pending", e.then(function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "fulfilled", n.value = e;
						}
					}, function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "rejected", n.reason = e;
						}
					});
				}
				switch (t.status) {
					case "fulfilled": return t.value;
					case "rejected": throw e = t.reason, Sa(e), e;
				}
				throw ba = t, pa;
		}
	}
	function ya(e) {
		try {
			var t = e._init;
			return t(e._payload);
		} catch (e) {
			throw typeof e == "object" && e && typeof e.then == "function" ? (ba = e, pa) : e;
		}
	}
	var ba = null;
	function xa() {
		if (ba === null) throw Error(s(459));
		var e = ba;
		return ba = null, e;
	}
	function Sa(e) {
		if (e === pa || e === ha) throw Error(s(483));
	}
	var Ca = null, wa = 0;
	function Ta(e) {
		var t = wa;
		return wa += 1, Ca === null && (Ca = []), va(Ca, e, t);
	}
	function Ea(e, t) {
		t = t.props.ref, e.ref = t === void 0 ? null : t;
	}
	function Da(e, t) {
		throw t.$$typeof === g ? Error(s(525)) : (e = Object.prototype.toString.call(t), Error(s(31, e === "[object Object]" ? "object with keys {" + Object.keys(t).join(", ") + "}" : e)));
	}
	function Oa(e) {
		function t(t, n) {
			if (e) {
				var r = t.deletions;
				r === null ? (t.deletions = [n], t.flags |= 16) : r.push(n);
			}
		}
		function n(n, r) {
			if (!e) return null;
			for (; r !== null;) t(n, r), r = r.sibling;
			return null;
		}
		function r(e) {
			for (var t = /* @__PURE__ */ new Map(); e !== null;) e.key === null ? t.set(e.index, e) : t.set(e.key, e), e = e.sibling;
			return t;
		}
		function i(e, t) {
			return e = ei(e, t), e.index = 0, e.sibling = null, e;
		}
		function a(t, n, r) {
			return t.index = r, e ? (r = t.alternate, r === null ? (t.flags |= 67108866, n) : (r = r.index, r < n ? (t.flags |= 67108866, n) : r)) : (t.flags |= 1048576, n);
		}
		function o(t) {
			return e && t.alternate === null && (t.flags |= 67108866), t;
		}
		function c(e, t, n, r) {
			return t === null || t.tag !== 6 ? (t = ii(n, e.mode, r), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function l(e, t, n, r) {
			var a = n.type;
			return a === y ? d(e, t, n.props.children, r, n.key) : t !== null && (t.elementType === a || typeof a == "object" && a && a.$$typeof === O && ya(a) === t.type) ? (t = i(t, n.props), Ea(t, n), t.return = e, t) : (t = ni(n.type, n.key, n.props, null, e.mode, r), Ea(t, n), t.return = e, t);
		}
		function u(e, t, n, r) {
			return t === null || t.tag !== 4 || t.stateNode.containerInfo !== n.containerInfo || t.stateNode.implementation !== n.implementation ? (t = oi(n, e.mode, r), t.return = e, t) : (t = i(t, n.children || []), t.return = e, t);
		}
		function d(e, t, n, r, a) {
			return t === null || t.tag !== 7 ? (t = ri(n, e.mode, r, a), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function f(e, t, n) {
			if (typeof t == "string" && t !== "" || typeof t == "number" || typeof t == "bigint") return t = ii("" + t, e.mode, n), t.return = e, t;
			if (typeof t == "object" && t) {
				switch (t.$$typeof) {
					case _: return n = ni(t.type, t.key, t.props, null, e.mode, n), Ea(n, t), n.return = e, n;
					case v: return t = oi(t, e.mode, n), t.return = e, t;
					case O: return t = ya(t), f(e, t, n);
				}
				if (F(t) || M(t)) return t = ri(t, e.mode, n, null), t.return = e, t;
				if (typeof t.then == "function") return f(e, Ta(t), n);
				if (t.$$typeof === C) return f(e, qi(e, t), n);
				Da(e, t);
			}
			return null;
		}
		function p(e, t, n, r) {
			var i = t === null ? null : t.key;
			if (typeof n == "string" && n !== "" || typeof n == "number" || typeof n == "bigint") return i === null ? c(e, t, "" + n, r) : null;
			if (typeof n == "object" && n) {
				switch (n.$$typeof) {
					case _: return n.key === i ? l(e, t, n, r) : null;
					case v: return n.key === i ? u(e, t, n, r) : null;
					case O: return n = ya(n), p(e, t, n, r);
				}
				if (F(n) || M(n)) return i === null ? d(e, t, n, r, null) : null;
				if (typeof n.then == "function") return p(e, t, Ta(n), r);
				if (n.$$typeof === C) return p(e, t, qi(e, n), r);
				Da(e, n);
			}
			return null;
		}
		function m(e, t, n, r, i) {
			if (typeof r == "string" && r !== "" || typeof r == "number" || typeof r == "bigint") return e = e.get(n) || null, c(t, e, "" + r, i);
			if (typeof r == "object" && r) {
				switch (r.$$typeof) {
					case _: return e = e.get(r.key === null ? n : r.key) || null, l(t, e, r, i);
					case v: return e = e.get(r.key === null ? n : r.key) || null, u(t, e, r, i);
					case O: return r = ya(r), m(e, t, n, r, i);
				}
				if (F(r) || M(r)) return e = e.get(n) || null, d(t, e, r, i, null);
				if (typeof r.then == "function") return m(e, t, n, Ta(r), i);
				if (r.$$typeof === C) return m(e, t, n, qi(t, r), i);
				Da(t, r);
			}
			return null;
		}
		function h(i, o, s, c) {
			for (var l = null, u = null, d = o, h = o = 0, g = null; d !== null && h < s.length; h++) {
				d.index > h ? (g = d, d = null) : g = d.sibling;
				var _ = p(i, d, s[h], c);
				if (_ === null) {
					d === null && (d = g);
					break;
				}
				e && d && _.alternate === null && t(i, d), o = a(_, o, h), u === null ? l = _ : u.sibling = _, u = _, d = g;
			}
			if (h === s.length) return n(i, d), Ti && vi(i, h), l;
			if (d === null) {
				for (; h < s.length; h++) d = f(i, s[h], c), d !== null && (o = a(d, o, h), u === null ? l = d : u.sibling = d, u = d);
				return Ti && vi(i, h), l;
			}
			for (d = r(d); h < s.length; h++) g = m(d, i, h, s[h], c), g !== null && (e && g.alternate !== null && d.delete(g.key === null ? h : g.key), o = a(g, o, h), u === null ? l = g : u.sibling = g, u = g);
			return e && d.forEach(function(e) {
				return t(i, e);
			}), Ti && vi(i, h), l;
		}
		function g(i, o, c, l) {
			if (c == null) throw Error(s(151));
			for (var u = null, d = null, h = o, g = o = 0, _ = null, v = c.next(); h !== null && !v.done; g++, v = c.next()) {
				h.index > g ? (_ = h, h = null) : _ = h.sibling;
				var y = p(i, h, v.value, l);
				if (y === null) {
					h === null && (h = _);
					break;
				}
				e && h && y.alternate === null && t(i, h), o = a(y, o, g), d === null ? u = y : d.sibling = y, d = y, h = _;
			}
			if (v.done) return n(i, h), Ti && vi(i, g), u;
			if (h === null) {
				for (; !v.done; g++, v = c.next()) v = f(i, v.value, l), v !== null && (o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
				return Ti && vi(i, g), u;
			}
			for (h = r(h); !v.done; g++, v = c.next()) v = m(h, i, g, v.value, l), v !== null && (e && v.alternate !== null && h.delete(v.key === null ? g : v.key), o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
			return e && h.forEach(function(e) {
				return t(i, e);
			}), Ti && vi(i, g), u;
		}
		function b(e, r, a, c) {
			if (typeof a == "object" && a && a.type === y && a.key === null && (a = a.props.children), typeof a == "object" && a) {
				switch (a.$$typeof) {
					case _:
						a: {
							for (var l = a.key; r !== null;) {
								if (r.key === l) {
									if (l = a.type, l === y) {
										if (r.tag === 7) {
											n(e, r.sibling), c = i(r, a.props.children), c.return = e, e = c;
											break a;
										}
									} else if (r.elementType === l || typeof l == "object" && l && l.$$typeof === O && ya(l) === r.type) {
										n(e, r.sibling), c = i(r, a.props), Ea(c, a), c.return = e, e = c;
										break a;
									}
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							a.type === y ? (c = ri(a.props.children, e.mode, c, a.key), c.return = e, e = c) : (c = ni(a.type, a.key, a.props, null, e.mode, c), Ea(c, a), c.return = e, e = c);
						}
						return o(e);
					case v:
						a: {
							for (l = a.key; r !== null;) {
								if (r.key === l) if (r.tag === 4 && r.stateNode.containerInfo === a.containerInfo && r.stateNode.implementation === a.implementation) {
									n(e, r.sibling), c = i(r, a.children || []), c.return = e, e = c;
									break a;
								} else {
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							c = oi(a, e.mode, c), c.return = e, e = c;
						}
						return o(e);
					case O: return a = ya(a), b(e, r, a, c);
				}
				if (F(a)) return h(e, r, a, c);
				if (M(a)) {
					if (l = M(a), typeof l != "function") throw Error(s(150));
					return a = l.call(a), g(e, r, a, c);
				}
				if (typeof a.then == "function") return b(e, r, Ta(a), c);
				if (a.$$typeof === C) return b(e, r, qi(e, a), c);
				Da(e, a);
			}
			return typeof a == "string" && a !== "" || typeof a == "number" || typeof a == "bigint" ? (a = "" + a, r !== null && r.tag === 6 ? (n(e, r.sibling), c = i(r, a), c.return = e, e = c) : (n(e, r), c = ii(a, e.mode, c), c.return = e, e = c), o(e)) : n(e, r);
		}
		return function(e, t, n, r) {
			try {
				wa = 0;
				var i = b(e, t, n, r);
				return Ca = null, i;
			} catch (t) {
				if (t === pa || t === ha) throw t;
				var a = Qr(29, t, null, e.mode);
				return a.lanes = r, a.return = e, a;
			}
		};
	}
	var ka = Oa(!0), Aa = Oa(!1), ja = !1;
	function Ma(e) {
		e.updateQueue = {
			baseState: e.memoizedState,
			firstBaseUpdate: null,
			lastBaseUpdate: null,
			shared: {
				pending: null,
				lanes: 0,
				hiddenCallbacks: null
			},
			callbacks: null
		};
	}
	function Na(e, t) {
		e = e.updateQueue, t.updateQueue === e && (t.updateQueue = {
			baseState: e.baseState,
			firstBaseUpdate: e.firstBaseUpdate,
			lastBaseUpdate: e.lastBaseUpdate,
			shared: e.shared,
			callbacks: null
		});
	}
	function Pa(e) {
		return {
			lane: e,
			tag: 0,
			payload: null,
			callback: null,
			next: null
		};
	}
	function Fa(e, t, n) {
		var r = e.updateQueue;
		if (r === null) return null;
		if (r = r.shared, Pl & 2) {
			var i = r.pending;
			return i === null ? t.next = t : (t.next = i.next, i.next = t), r.pending = t, t = Yr(e), Jr(e, null, n), t;
		}
		return Gr(e, r, t, n), Yr(e);
	}
	function Ia(e, t, n) {
		if (t = t.updateQueue, t !== null && (t = t.shared, n & 4194048)) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, We(e, n);
		}
	}
	function La(e, t) {
		var n = e.updateQueue, r = e.alternate;
		if (r !== null && (r = r.updateQueue, n === r)) {
			var i = null, a = null;
			if (n = n.firstBaseUpdate, n !== null) {
				do {
					var o = {
						lane: n.lane,
						tag: n.tag,
						payload: n.payload,
						callback: null,
						next: null
					};
					a === null ? i = a = o : a = a.next = o, n = n.next;
				} while (n !== null);
				a === null ? i = a = t : a = a.next = t;
			} else i = a = t;
			n = {
				baseState: r.baseState,
				firstBaseUpdate: i,
				lastBaseUpdate: a,
				shared: r.shared,
				callbacks: r.callbacks
			}, e.updateQueue = n;
			return;
		}
		e = n.lastBaseUpdate, e === null ? n.firstBaseUpdate = t : e.next = t, n.lastBaseUpdate = t;
	}
	var Ra = !1;
	function za() {
		if (Ra) {
			var e = ia;
			if (e !== null) throw e;
		}
	}
	function Ba(e, t, n, r) {
		Ra = !1;
		var i = e.updateQueue;
		ja = !1;
		var a = i.firstBaseUpdate, o = i.lastBaseUpdate, s = i.shared.pending;
		if (s !== null) {
			i.shared.pending = null;
			var c = s, l = c.next;
			c.next = null, o === null ? a = l : o.next = l, o = c;
			var u = e.alternate;
			u !== null && (u = u.updateQueue, s = u.lastBaseUpdate, s !== o && (s === null ? u.firstBaseUpdate = l : s.next = l, u.lastBaseUpdate = c));
		}
		if (a !== null) {
			var d = i.baseState;
			o = 0, u = l = c = null, s = a;
			do {
				var f = s.lane & -536870913, p = f !== s.lane;
				if (p ? (Q & f) === f : (r & f) === f) {
					f !== 0 && f === ra && (Ra = !0), u !== null && (u = u.next = {
						lane: 0,
						tag: s.tag,
						payload: s.payload,
						callback: null,
						next: null
					});
					a: {
						var m = e, g = s;
						f = t;
						var _ = n;
						switch (g.tag) {
							case 1:
								if (m = g.payload, typeof m == "function") {
									d = m.call(_, d, f);
									break a;
								}
								d = m;
								break a;
							case 3: m.flags = m.flags & -65537 | 128;
							case 0:
								if (m = g.payload, f = typeof m == "function" ? m.call(_, d, f) : m, f == null) break a;
								d = h({}, d, f);
								break a;
							case 2: ja = !0;
						}
					}
					f = s.callback, f !== null && (e.flags |= 64, p && (e.flags |= 8192), p = i.callbacks, p === null ? i.callbacks = [f] : p.push(f));
				} else p = {
					lane: f,
					tag: s.tag,
					payload: s.payload,
					callback: s.callback,
					next: null
				}, u === null ? (l = u = p, c = d) : u = u.next = p, o |= f;
				if (s = s.next, s === null) {
					if (s = i.shared.pending, s === null) break;
					p = s, s = p.next, p.next = null, i.lastBaseUpdate = p, i.shared.pending = null;
				}
			} while (1);
			u === null && (c = d), i.baseState = c, i.firstBaseUpdate = l, i.lastBaseUpdate = u, a === null && (i.shared.lanes = 0), Ul |= o, e.lanes = o, e.memoizedState = d;
		}
	}
	function Va(e, t) {
		if (typeof e != "function") throw Error(s(191, e));
		e.call(t);
	}
	function Ha(e, t) {
		var n = e.callbacks;
		if (n !== null) for (e.callbacks = null, e = 0; e < n.length; e++) Va(n[e], t);
	}
	var Ua = V(null), Wa = V(0);
	function Ga(e, t) {
		e = Vl, U(Wa, e), U(Ua, t), Vl = e | t.baseLanes;
	}
	function Ka() {
		U(Wa, Vl), U(Ua, Ua.current);
	}
	function qa() {
		Vl = Wa.current, H(Ua), H(Wa);
	}
	var Ja = V(null), Ya = null;
	function Xa(e) {
		var t = e.alternate;
		U(to, to.current & 1), U(Ja, e), Ya === null && (t === null || Ua.current !== null || t.memoizedState !== null) && (Ya = e);
	}
	function Za(e) {
		U(to, to.current), U(Ja, e), Ya === null && (Ya = e);
	}
	function Qa(e) {
		e.tag === 22 ? (U(to, to.current), U(Ja, e), Ya === null && (Ya = e)) : $a(e);
	}
	function $a() {
		U(to, to.current), U(Ja, Ja.current);
	}
	function eo(e) {
		H(Ja), Ya === e && (Ya = null), H(to);
	}
	var to = V(0);
	function no(e) {
		for (var t = e; t !== null;) {
			if (t.tag === 13) {
				var n = t.memoizedState;
				if (n !== null && (n = n.dehydrated, n === null || af(n) || of(n))) return t;
			} else if (t.tag === 19 && (t.memoizedProps.revealOrder === "forwards" || t.memoizedProps.revealOrder === "backwards" || t.memoizedProps.revealOrder === "unstable_legacy-backwards" || t.memoizedProps.revealOrder === "together")) {
				if (t.flags & 128) return t;
			} else if (t.child !== null) {
				t.child.return = t, t = t.child;
				continue;
			}
			if (t === e) break;
			for (; t.sibling === null;) {
				if (t.return === null || t.return === e) return null;
				t = t.return;
			}
			t.sibling.return = t.return, t = t.sibling;
		}
		return null;
	}
	var ro = 0, Y = null, X = null, io = null, ao = !1, oo = !1, so = !1, co = 0, lo = 0, uo = null, fo = 0;
	function po() {
		throw Error(s(321));
	}
	function mo(e, t) {
		if (t === null) return !1;
		for (var n = 0; n < t.length && n < e.length; n++) if (!fr(e[n], t[n])) return !1;
		return !0;
	}
	function ho(e, t, n, r, i, a) {
		return ro = a, Y = t, t.memoizedState = null, t.updateQueue = null, t.lanes = 0, I.H = e === null || e.memoizedState === null ? Ms : Ns, so = !1, a = n(r, i), so = !1, oo && (a = _o(t, n, r, i)), go(e), a;
	}
	function go(e) {
		I.H = js;
		var t = X !== null && X.next !== null;
		if (ro = 0, io = X = Y = null, ao = !1, lo = 0, uo = null, t) throw Error(s(300));
		e === null || Xs || (e = e.dependencies, e !== null && Wi(e) && (Xs = !0));
	}
	function _o(e, t, n, r) {
		Y = e;
		var i = 0;
		do {
			if (oo && (uo = null), lo = 0, oo = !1, 25 <= i) throw Error(s(301));
			if (i += 1, io = X = null, e.updateQueue != null) {
				var a = e.updateQueue;
				a.lastEffect = null, a.events = null, a.stores = null, a.memoCache != null && (a.memoCache.index = 0);
			}
			I.H = Ps, a = t(n, r);
		} while (oo);
		return a;
	}
	function vo() {
		var e = I.H, t = e.useState()[0];
		return t = typeof t.then == "function" ? To(t) : t, e = e.useState()[0], (X === null ? null : X.memoizedState) !== e && (Y.flags |= 1024), t;
	}
	function yo() {
		var e = co !== 0;
		return co = 0, e;
	}
	function bo(e, t, n) {
		t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~n;
	}
	function xo(e) {
		if (ao) {
			for (e = e.memoizedState; e !== null;) {
				var t = e.queue;
				t !== null && (t.pending = null), e = e.next;
			}
			ao = !1;
		}
		ro = 0, io = X = Y = null, oo = !1, lo = co = 0, uo = null;
	}
	function So() {
		var e = {
			memoizedState: null,
			baseState: null,
			baseQueue: null,
			queue: null,
			next: null
		};
		return io === null ? Y.memoizedState = io = e : io = io.next = e, io;
	}
	function Co() {
		if (X === null) {
			var e = Y.alternate;
			e = e === null ? null : e.memoizedState;
		} else e = X.next;
		var t = io === null ? Y.memoizedState : io.next;
		if (t !== null) io = t, X = e;
		else {
			if (e === null) throw Y.alternate === null ? Error(s(467)) : Error(s(310));
			X = e, e = {
				memoizedState: X.memoizedState,
				baseState: X.baseState,
				baseQueue: X.baseQueue,
				queue: X.queue,
				next: null
			}, io === null ? Y.memoizedState = io = e : io = io.next = e;
		}
		return io;
	}
	function wo() {
		return {
			lastEffect: null,
			events: null,
			stores: null,
			memoCache: null
		};
	}
	function To(e) {
		var t = lo;
		return lo += 1, uo === null && (uo = []), e = va(uo, e, t), t = Y, (io === null ? t.memoizedState : io.next) === null && (t = t.alternate, I.H = t === null || t.memoizedState === null ? Ms : Ns), e;
	}
	function Eo(e) {
		if (typeof e == "object" && e) {
			if (typeof e.then == "function") return To(e);
			if (e.$$typeof === C) return Ki(e);
		}
		throw Error(s(438, String(e)));
	}
	function Do(e) {
		var t = null, n = Y.updateQueue;
		if (n !== null && (t = n.memoCache), t == null) {
			var r = Y.alternate;
			r !== null && (r = r.updateQueue, r !== null && (r = r.memoCache, r != null && (t = {
				data: r.data.map(function(e) {
					return e.slice();
				}),
				index: 0
			})));
		}
		if (t ??= {
			data: [],
			index: 0
		}, n === null && (n = wo(), Y.updateQueue = n), n.memoCache = t, n = t.data[t.index], n === void 0) for (n = t.data[t.index] = Array(e), r = 0; r < e; r++) n[r] = A;
		return t.index++, n;
	}
	function Oo(e, t) {
		return typeof t == "function" ? t(e) : t;
	}
	function ko(e) {
		return Ao(Co(), X, e);
	}
	function Ao(e, t, n) {
		var r = e.queue;
		if (r === null) throw Error(s(311));
		r.lastRenderedReducer = n;
		var i = e.baseQueue, a = r.pending;
		if (a !== null) {
			if (i !== null) {
				var o = i.next;
				i.next = a.next, a.next = o;
			}
			t.baseQueue = i = a, r.pending = null;
		}
		if (a = e.baseState, i === null) e.memoizedState = a;
		else {
			t = i.next;
			var c = o = null, l = null, u = t, d = !1;
			do {
				var f = u.lane & -536870913;
				if (f === u.lane ? (ro & f) === f : (Q & f) === f) {
					var p = u.revertLane;
					if (p === 0) l !== null && (l = l.next = {
						lane: 0,
						revertLane: 0,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}), f === ra && (d = !0);
					else if ((ro & p) === p) {
						u = u.next, p === ra && (d = !0);
						continue;
					} else f = {
						lane: 0,
						revertLane: u.revertLane,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}, l === null ? (c = l = f, o = a) : l = l.next = f, Y.lanes |= p, Ul |= p;
					f = u.action, so && n(a, f), a = u.hasEagerState ? u.eagerState : n(a, f);
				} else p = {
					lane: f,
					revertLane: u.revertLane,
					gesture: u.gesture,
					action: u.action,
					hasEagerState: u.hasEagerState,
					eagerState: u.eagerState,
					next: null
				}, l === null ? (c = l = p, o = a) : l = l.next = p, Y.lanes |= f, Ul |= f;
				u = u.next;
			} while (u !== null && u !== t);
			if (l === null ? o = a : l.next = c, !fr(a, e.memoizedState) && (Xs = !0, d && (n = ia, n !== null))) throw n;
			e.memoizedState = a, e.baseState = o, e.baseQueue = l, r.lastRenderedState = a;
		}
		return i === null && (r.lanes = 0), [e.memoizedState, r.dispatch];
	}
	function jo(e) {
		var t = Co(), n = t.queue;
		if (n === null) throw Error(s(311));
		n.lastRenderedReducer = e;
		var r = n.dispatch, i = n.pending, a = t.memoizedState;
		if (i !== null) {
			n.pending = null;
			var o = i = i.next;
			do
				a = e(a, o.action), o = o.next;
			while (o !== i);
			fr(a, t.memoizedState) || (Xs = !0), t.memoizedState = a, t.baseQueue === null && (t.baseState = a), n.lastRenderedState = a;
		}
		return [a, r];
	}
	function Mo(e, t, n) {
		var r = Y, i = Co(), a = Ti;
		if (a) {
			if (n === void 0) throw Error(s(407));
			n = n();
		} else n = t();
		var o = !fr((X || i).memoizedState, n);
		if (o && (i.memoizedState = n, Xs = !0), i = i.queue, rs(Fo.bind(null, r, i, e), [e]), i.getSnapshot !== t || o || io !== null && io.memoizedState.tag & 1) {
			if (r.flags |= 2048, Qo(9, { destroy: void 0 }, Po.bind(null, r, i, n, t), null), Fl === null) throw Error(s(349));
			a || ro & 127 || No(r, t, n);
		}
		return n;
	}
	function No(e, t, n) {
		e.flags |= 16384, e = {
			getSnapshot: t,
			value: n
		}, t = Y.updateQueue, t === null ? (t = wo(), Y.updateQueue = t, t.stores = [e]) : (n = t.stores, n === null ? t.stores = [e] : n.push(e));
	}
	function Po(e, t, n, r) {
		t.value = n, t.getSnapshot = r, Io(t) && Lo(e);
	}
	function Fo(e, t, n) {
		return n(function() {
			Io(t) && Lo(e);
		});
	}
	function Io(e) {
		var t = e.getSnapshot;
		e = e.value;
		try {
			var n = t();
			return !fr(e, n);
		} catch {
			return !0;
		}
	}
	function Lo(e) {
		var t = qr(e, 2);
		t !== null && pu(t, e, 2);
	}
	function Ro(e) {
		var t = So();
		if (typeof e == "function") {
			var n = e;
			if (e = n(), so) {
				De(!0);
				try {
					n();
				} finally {
					De(!1);
				}
			}
		}
		return t.memoizedState = t.baseState = e, t.queue = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: Oo,
			lastRenderedState: e
		}, t;
	}
	function zo(e, t, n, r) {
		return e.baseState = n, Ao(e, X, typeof r == "function" ? r : Oo);
	}
	function Bo(e, t, n, r, i) {
		if (Os(e)) throw Error(s(485));
		if (e = t.action, e !== null) {
			var a = {
				payload: i,
				action: e,
				next: null,
				isTransition: !0,
				status: "pending",
				value: null,
				reason: null,
				listeners: [],
				then: function(e) {
					a.listeners.push(e);
				}
			};
			I.T === null ? a.isTransition = !1 : n(!0), r(a), n = t.pending, n === null ? (a.next = t.pending = a, Vo(t, a)) : (a.next = n.next, t.pending = n.next = a);
		}
	}
	function Vo(e, t) {
		var n = t.action, r = t.payload, i = e.state;
		if (t.isTransition) {
			var a = I.T, o = {};
			I.T = o;
			try {
				var s = n(i, r), c = I.S;
				c !== null && c(o, s), Ho(e, t, s);
			} catch (n) {
				Wo(e, t, n);
			} finally {
				a !== null && o.types !== null && (a.types = o.types), I.T = a;
			}
		} else try {
			a = n(i, r), Ho(e, t, a);
		} catch (n) {
			Wo(e, t, n);
		}
	}
	function Ho(e, t, n) {
		typeof n == "object" && n && typeof n.then == "function" ? n.then(function(n) {
			Uo(e, t, n);
		}, function(n) {
			return Wo(e, t, n);
		}) : Uo(e, t, n);
	}
	function Uo(e, t, n) {
		t.status = "fulfilled", t.value = n, Go(t), e.state = n, t = e.pending, t !== null && (n = t.next, n === t ? e.pending = null : (n = n.next, t.next = n, Vo(e, n)));
	}
	function Wo(e, t, n) {
		var r = e.pending;
		if (e.pending = null, r !== null) {
			r = r.next;
			do
				t.status = "rejected", t.reason = n, Go(t), t = t.next;
			while (t !== r);
		}
		e.action = null;
	}
	function Go(e) {
		e = e.listeners;
		for (var t = 0; t < e.length; t++) (0, e[t])();
	}
	function Ko(e, t) {
		return t;
	}
	function qo(e, t) {
		if (Ti) {
			var n = Fl.formState;
			if (n !== null) {
				a: {
					var r = Y;
					if (Ti) {
						if (wi) {
							b: {
								for (var i = wi, a = Di; i.nodeType !== 8;) {
									if (!a) {
										i = null;
										break b;
									}
									if (i = cf(i.nextSibling), i === null) {
										i = null;
										break b;
									}
								}
								a = i.data, i = a === "F!" || a === "F" ? i : null;
							}
							if (i) {
								wi = cf(i.nextSibling), r = i.data === "F!";
								break a;
							}
						}
						ki(r);
					}
					r = !1;
				}
				r && (t = n[0]);
			}
		}
		return n = So(), n.memoizedState = n.baseState = t, r = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: Ko,
			lastRenderedState: t
		}, n.queue = r, n = Ts.bind(null, Y, r), r.dispatch = n, r = Ro(!1), a = Ds.bind(null, Y, !1, r.queue), r = So(), i = {
			state: t,
			dispatch: null,
			action: e,
			pending: null
		}, r.queue = i, n = Bo.bind(null, Y, i, a, n), i.dispatch = n, r.memoizedState = e, [
			t,
			n,
			!1
		];
	}
	function Jo(e) {
		return Yo(Co(), X, e);
	}
	function Yo(e, t, n) {
		if (t = Ao(e, t, Ko)[0], e = ko(Oo)[0], typeof t == "object" && t && typeof t.then == "function") try {
			var r = To(t);
		} catch (e) {
			throw e === pa ? ha : e;
		}
		else r = t;
		t = Co();
		var i = t.queue, a = i.dispatch;
		return n !== t.memoizedState && (Y.flags |= 2048, Qo(9, { destroy: void 0 }, Xo.bind(null, i, n), null)), [
			r,
			a,
			e
		];
	}
	function Xo(e, t) {
		e.action = t;
	}
	function Zo(e) {
		var t = Co(), n = X;
		if (n !== null) return Yo(t, n, e);
		Co(), t = t.memoizedState, n = Co();
		var r = n.queue.dispatch;
		return n.memoizedState = e, [
			t,
			r,
			!1
		];
	}
	function Qo(e, t, n, r) {
		return e = {
			tag: e,
			create: n,
			deps: r,
			inst: t,
			next: null
		}, t = Y.updateQueue, t === null && (t = wo(), Y.updateQueue = t), n = t.lastEffect, n === null ? t.lastEffect = e.next = e : (r = n.next, n.next = e, e.next = r, t.lastEffect = e), e;
	}
	function $o() {
		return Co().memoizedState;
	}
	function es(e, t, n, r) {
		var i = So();
		Y.flags |= e, i.memoizedState = Qo(1 | t, { destroy: void 0 }, n, r === void 0 ? null : r);
	}
	function ts(e, t, n, r) {
		var i = Co();
		r = r === void 0 ? null : r;
		var a = i.memoizedState.inst;
		X !== null && r !== null && mo(r, X.memoizedState.deps) ? i.memoizedState = Qo(t, a, n, r) : (Y.flags |= e, i.memoizedState = Qo(1 | t, a, n, r));
	}
	function ns(e, t) {
		es(8390656, 8, e, t);
	}
	function rs(e, t) {
		ts(2048, 8, e, t);
	}
	function is(e) {
		Y.flags |= 4;
		var t = Y.updateQueue;
		if (t === null) t = wo(), Y.updateQueue = t, t.events = [e];
		else {
			var n = t.events;
			n === null ? t.events = [e] : n.push(e);
		}
	}
	function as(e) {
		var t = Co().memoizedState;
		return is({
			ref: t,
			nextImpl: e
		}), function() {
			if (Pl & 2) throw Error(s(440));
			return t.impl.apply(void 0, arguments);
		};
	}
	function os(e, t) {
		return ts(4, 2, e, t);
	}
	function ss(e, t) {
		return ts(4, 4, e, t);
	}
	function cs(e, t) {
		if (typeof t == "function") {
			e = e();
			var n = t(e);
			return function() {
				typeof n == "function" ? n() : t(null);
			};
		}
		if (t != null) return e = e(), t.current = e, function() {
			t.current = null;
		};
	}
	function ls(e, t, n) {
		n = n == null ? null : n.concat([e]), ts(4, 4, cs.bind(null, t, e), n);
	}
	function us() {}
	function ds(e, t) {
		var n = Co();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		return t !== null && mo(t, r[1]) ? r[0] : (n.memoizedState = [e, t], e);
	}
	function fs(e, t) {
		var n = Co();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		if (t !== null && mo(t, r[1])) return r[0];
		if (r = e(), so) {
			De(!0);
			try {
				e();
			} finally {
				De(!1);
			}
		}
		return n.memoizedState = [r, t], r;
	}
	function ps(e, t, n) {
		return n === void 0 || ro & 1073741824 && !(Q & 261930) ? e.memoizedState = t : (e.memoizedState = n, e = fu(), Y.lanes |= e, Ul |= e, n);
	}
	function ms(e, t, n, r) {
		return fr(n, t) ? n : Ua.current === null ? !(ro & 42) || ro & 1073741824 && !(Q & 261930) ? (Xs = !0, e.memoizedState = n) : (e = fu(), Y.lanes |= e, Ul |= e, t) : (e = ps(e, n, r), fr(e, t) || (Xs = !0), e);
	}
	function hs(e, t, n, r, i) {
		var a = L.p;
		L.p = a !== 0 && 8 > a ? a : 8;
		var o = I.T, s = {};
		I.T = s, Ds(e, !1, t, n);
		try {
			var c = i(), l = I.S;
			l !== null && l(s, c), typeof c == "object" && c && typeof c.then == "function" ? Es(e, t, sa(c, r), du(e)) : Es(e, t, r, du(e));
		} catch (n) {
			Es(e, t, {
				then: function() {},
				status: "rejected",
				reason: n
			}, du());
		} finally {
			L.p = a, o !== null && s.types !== null && (o.types = s.types), I.T = o;
		}
	}
	function gs() {}
	function _s(e, t, n, r) {
		if (e.tag !== 5) throw Error(s(476));
		var i = vs(e).queue;
		hs(e, i, t, R, n === null ? gs : function() {
			return ys(e), n(r);
		});
	}
	function vs(e) {
		var t = e.memoizedState;
		if (t !== null) return t;
		t = {
			memoizedState: R,
			baseState: R,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: Oo,
				lastRenderedState: R
			},
			next: null
		};
		var n = {};
		return t.next = {
			memoizedState: n,
			baseState: n,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: Oo,
				lastRenderedState: n
			},
			next: null
		}, e.memoizedState = t, e = e.alternate, e !== null && (e.memoizedState = t), t;
	}
	function ys(e) {
		var t = vs(e);
		t.next === null && (t = e.alternate.memoizedState), Es(e, t.next.queue, {}, du());
	}
	function bs() {
		return Ki(Qf);
	}
	function xs() {
		return Co().memoizedState;
	}
	function Ss() {
		return Co().memoizedState;
	}
	function Cs(e) {
		for (var t = e.return; t !== null;) {
			switch (t.tag) {
				case 24:
				case 3:
					var n = du();
					e = Pa(n);
					var r = Fa(t, e, n);
					r !== null && (pu(r, t, n), Ia(r, t, n)), t = { cache: $i() }, e.payload = t;
					return;
			}
			t = t.return;
		}
	}
	function ws(e, t, n) {
		var r = du();
		n = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, Os(e) ? ks(t, n) : (n = Kr(e, t, n, r), n !== null && (pu(n, e, r), As(n, t, r)));
	}
	function Ts(e, t, n) {
		Es(e, t, n, du());
	}
	function Es(e, t, n, r) {
		var i = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		};
		if (Os(e)) ks(t, i);
		else {
			var a = e.alternate;
			if (e.lanes === 0 && (a === null || a.lanes === 0) && (a = t.lastRenderedReducer, a !== null)) try {
				var o = t.lastRenderedState, s = a(o, n);
				if (i.hasEagerState = !0, i.eagerState = s, fr(s, o)) return Gr(e, t, i, 0), Fl === null && Wr(), !1;
			} catch {}
			if (n = Kr(e, t, i, r), n !== null) return pu(n, e, r), As(n, t, r), !0;
		}
		return !1;
	}
	function Ds(e, t, n, r) {
		if (r = {
			lane: 2,
			revertLane: ud(),
			gesture: null,
			action: r,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, Os(e)) {
			if (t) throw Error(s(479));
		} else t = Kr(e, n, r, 2), t !== null && pu(t, e, 2);
	}
	function Os(e) {
		var t = e.alternate;
		return e === Y || t !== null && t === Y;
	}
	function ks(e, t) {
		oo = ao = !0;
		var n = e.pending;
		n === null ? t.next = t : (t.next = n.next, n.next = t), e.pending = t;
	}
	function As(e, t, n) {
		if (n & 4194048) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, We(e, n);
		}
	}
	var js = {
		readContext: Ki,
		use: Eo,
		useCallback: po,
		useContext: po,
		useEffect: po,
		useImperativeHandle: po,
		useLayoutEffect: po,
		useInsertionEffect: po,
		useMemo: po,
		useReducer: po,
		useRef: po,
		useState: po,
		useDebugValue: po,
		useDeferredValue: po,
		useTransition: po,
		useSyncExternalStore: po,
		useId: po,
		useHostTransitionStatus: po,
		useFormState: po,
		useActionState: po,
		useOptimistic: po,
		useMemoCache: po,
		useCacheRefresh: po
	};
	js.useEffectEvent = po;
	var Ms = {
		readContext: Ki,
		use: Eo,
		useCallback: function(e, t) {
			return So().memoizedState = [e, t === void 0 ? null : t], e;
		},
		useContext: Ki,
		useEffect: ns,
		useImperativeHandle: function(e, t, n) {
			n = n == null ? null : n.concat([e]), es(4194308, 4, cs.bind(null, t, e), n);
		},
		useLayoutEffect: function(e, t) {
			return es(4194308, 4, e, t);
		},
		useInsertionEffect: function(e, t) {
			es(4, 2, e, t);
		},
		useMemo: function(e, t) {
			var n = So();
			t = t === void 0 ? null : t;
			var r = e();
			if (so) {
				De(!0);
				try {
					e();
				} finally {
					De(!1);
				}
			}
			return n.memoizedState = [r, t], r;
		},
		useReducer: function(e, t, n) {
			var r = So();
			if (n !== void 0) {
				var i = n(t);
				if (so) {
					De(!0);
					try {
						n(t);
					} finally {
						De(!1);
					}
				}
			} else i = t;
			return r.memoizedState = r.baseState = i, e = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: e,
				lastRenderedState: i
			}, r.queue = e, e = e.dispatch = ws.bind(null, Y, e), [r.memoizedState, e];
		},
		useRef: function(e) {
			var t = So();
			return e = { current: e }, t.memoizedState = e;
		},
		useState: function(e) {
			e = Ro(e);
			var t = e.queue, n = Ts.bind(null, Y, t);
			return t.dispatch = n, [e.memoizedState, n];
		},
		useDebugValue: us,
		useDeferredValue: function(e, t) {
			return ps(So(), e, t);
		},
		useTransition: function() {
			var e = Ro(!1);
			return e = hs.bind(null, Y, e.queue, !0, !1), So().memoizedState = e, [!1, e];
		},
		useSyncExternalStore: function(e, t, n) {
			var r = Y, i = So();
			if (Ti) {
				if (n === void 0) throw Error(s(407));
				n = n();
			} else {
				if (n = t(), Fl === null) throw Error(s(349));
				Q & 127 || No(r, t, n);
			}
			i.memoizedState = n;
			var a = {
				value: n,
				getSnapshot: t
			};
			return i.queue = a, ns(Fo.bind(null, r, a, e), [e]), r.flags |= 2048, Qo(9, { destroy: void 0 }, Po.bind(null, r, a, n, t), null), n;
		},
		useId: function() {
			var e = So(), t = Fl.identifierPrefix;
			if (Ti) {
				var n = _i, r = gi;
				n = (r & ~(1 << 32 - Oe(r) - 1)).toString(32) + n, t = "_" + t + "R_" + n, n = co++, 0 < n && (t += "H" + n.toString(32)), t += "_";
			} else n = fo++, t = "_" + t + "r_" + n.toString(32) + "_";
			return e.memoizedState = t;
		},
		useHostTransitionStatus: bs,
		useFormState: qo,
		useActionState: qo,
		useOptimistic: function(e) {
			var t = So();
			t.memoizedState = t.baseState = e;
			var n = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: null,
				lastRenderedState: null
			};
			return t.queue = n, t = Ds.bind(null, Y, !0, n), n.dispatch = t, [e, t];
		},
		useMemoCache: Do,
		useCacheRefresh: function() {
			return So().memoizedState = Cs.bind(null, Y);
		},
		useEffectEvent: function(e) {
			var t = So(), n = { impl: e };
			return t.memoizedState = n, function() {
				if (Pl & 2) throw Error(s(440));
				return n.impl.apply(void 0, arguments);
			};
		}
	}, Ns = {
		readContext: Ki,
		use: Eo,
		useCallback: ds,
		useContext: Ki,
		useEffect: rs,
		useImperativeHandle: ls,
		useInsertionEffect: os,
		useLayoutEffect: ss,
		useMemo: fs,
		useReducer: ko,
		useRef: $o,
		useState: function() {
			return ko(Oo);
		},
		useDebugValue: us,
		useDeferredValue: function(e, t) {
			return ms(Co(), X.memoizedState, e, t);
		},
		useTransition: function() {
			var e = ko(Oo)[0], t = Co().memoizedState;
			return [typeof e == "boolean" ? e : To(e), t];
		},
		useSyncExternalStore: Mo,
		useId: xs,
		useHostTransitionStatus: bs,
		useFormState: Jo,
		useActionState: Jo,
		useOptimistic: function(e, t) {
			return zo(Co(), X, e, t);
		},
		useMemoCache: Do,
		useCacheRefresh: Ss
	};
	Ns.useEffectEvent = as;
	var Ps = {
		readContext: Ki,
		use: Eo,
		useCallback: ds,
		useContext: Ki,
		useEffect: rs,
		useImperativeHandle: ls,
		useInsertionEffect: os,
		useLayoutEffect: ss,
		useMemo: fs,
		useReducer: jo,
		useRef: $o,
		useState: function() {
			return jo(Oo);
		},
		useDebugValue: us,
		useDeferredValue: function(e, t) {
			var n = Co();
			return X === null ? ps(n, e, t) : ms(n, X.memoizedState, e, t);
		},
		useTransition: function() {
			var e = jo(Oo)[0], t = Co().memoizedState;
			return [typeof e == "boolean" ? e : To(e), t];
		},
		useSyncExternalStore: Mo,
		useId: xs,
		useHostTransitionStatus: bs,
		useFormState: Zo,
		useActionState: Zo,
		useOptimistic: function(e, t) {
			var n = Co();
			return X === null ? (n.baseState = e, [e, n.queue.dispatch]) : zo(n, X, e, t);
		},
		useMemoCache: Do,
		useCacheRefresh: Ss
	};
	Ps.useEffectEvent = as;
	function Fs(e, t, n, r) {
		t = e.memoizedState, n = n(r, t), n = n == null ? t : h({}, t, n), e.memoizedState = n, e.lanes === 0 && (e.updateQueue.baseState = n);
	}
	var Is = {
		enqueueSetState: function(e, t, n) {
			e = e._reactInternals;
			var r = du(), i = Pa(r);
			i.payload = t, n != null && (i.callback = n), t = Fa(e, i, r), t !== null && (pu(t, e, r), Ia(t, e, r));
		},
		enqueueReplaceState: function(e, t, n) {
			e = e._reactInternals;
			var r = du(), i = Pa(r);
			i.tag = 1, i.payload = t, n != null && (i.callback = n), t = Fa(e, i, r), t !== null && (pu(t, e, r), Ia(t, e, r));
		},
		enqueueForceUpdate: function(e, t) {
			e = e._reactInternals;
			var n = du(), r = Pa(n);
			r.tag = 2, t != null && (r.callback = t), t = Fa(e, r, n), t !== null && (pu(t, e, n), Ia(t, e, n));
		}
	};
	function Ls(e, t, n, r, i, a, o) {
		return e = e.stateNode, typeof e.shouldComponentUpdate == "function" ? e.shouldComponentUpdate(r, a, o) : t.prototype && t.prototype.isPureReactComponent ? !pr(n, r) || !pr(i, a) : !0;
	}
	function Rs(e, t, n, r) {
		e = t.state, typeof t.componentWillReceiveProps == "function" && t.componentWillReceiveProps(n, r), typeof t.UNSAFE_componentWillReceiveProps == "function" && t.UNSAFE_componentWillReceiveProps(n, r), t.state !== e && Is.enqueueReplaceState(t, t.state, null);
	}
	function zs(e, t) {
		var n = t;
		if ("ref" in t) for (var r in n = {}, t) r !== "ref" && (n[r] = t[r]);
		if (e = e.defaultProps) for (var i in n === t && (n = h({}, n)), e) n[i] === void 0 && (n[i] = e[i]);
		return n;
	}
	function Bs(e) {
		Br(e);
	}
	function Vs(e) {
		console.error(e);
	}
	function Hs(e) {
		Br(e);
	}
	function Us(e, t) {
		try {
			var n = e.onUncaughtError;
			n(t.value, { componentStack: t.stack });
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Ws(e, t, n) {
		try {
			var r = e.onCaughtError;
			r(n.value, {
				componentStack: n.stack,
				errorBoundary: t.tag === 1 ? t.stateNode : null
			});
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Gs(e, t, n) {
		return n = Pa(n), n.tag = 3, n.payload = { element: null }, n.callback = function() {
			Us(e, t);
		}, n;
	}
	function Ks(e) {
		return e = Pa(e), e.tag = 3, e;
	}
	function qs(e, t, n, r) {
		var i = n.type.getDerivedStateFromError;
		if (typeof i == "function") {
			var a = r.value;
			e.payload = function() {
				return i(a);
			}, e.callback = function() {
				Ws(t, n, r);
			};
		}
		var o = n.stateNode;
		o !== null && typeof o.componentDidCatch == "function" && (e.callback = function() {
			Ws(t, n, r), typeof i != "function" && (tu === null ? tu = /* @__PURE__ */ new Set([this]) : tu.add(this));
			var e = r.stack;
			this.componentDidCatch(r.value, { componentStack: e === null ? "" : e });
		});
	}
	function Js(e, t, n, r, i) {
		if (n.flags |= 32768, typeof r == "object" && r && typeof r.then == "function") {
			if (t = n.alternate, t !== null && Ui(t, n, i, !0), n = Ja.current, n !== null) {
				switch (n.tag) {
					case 31:
					case 13: return Ya === null ? Tu() : n.alternate === null && Hl === 0 && (Hl = 3), n.flags &= -257, n.flags |= 65536, n.lanes = i, r === ga ? n.flags |= 16384 : (t = n.updateQueue, t === null ? n.updateQueue = /* @__PURE__ */ new Set([r]) : t.add(r), Wu(e, r, i)), !1;
					case 22: return n.flags |= 65536, r === ga ? n.flags |= 16384 : (t = n.updateQueue, t === null ? (t = {
						transitions: null,
						markerInstances: null,
						retryQueue: /* @__PURE__ */ new Set([r])
					}, n.updateQueue = t) : (n = t.retryQueue, n === null ? t.retryQueue = /* @__PURE__ */ new Set([r]) : n.add(r)), Wu(e, r, i)), !1;
				}
				throw Error(s(435, n.tag));
			}
			return Wu(e, r, i), Tu(), !1;
		}
		if (Ti) return t = Ja.current, t === null ? (r !== Oi && (t = Error(s(423), { cause: r }), Fi(ci(t, n))), e = e.current.alternate, e.flags |= 65536, i &= -i, e.lanes |= i, r = ci(r, n), i = Gs(e.stateNode, r, i), La(e, i), Hl !== 4 && (Hl = 2)) : (!(t.flags & 65536) && (t.flags |= 256), t.flags |= 65536, t.lanes = i, r !== Oi && (e = Error(s(422), { cause: r }), Fi(ci(e, n)))), !1;
		var a = Error(s(520), { cause: r });
		if (a = ci(a, n), Jl === null ? Jl = [a] : Jl.push(a), Hl !== 4 && (Hl = 2), t === null) return !0;
		r = ci(r, n), n = t;
		do {
			switch (n.tag) {
				case 3: return n.flags |= 65536, e = i & -i, n.lanes |= e, e = Gs(n.stateNode, r, e), La(n, e), !1;
				case 1: if (t = n.type, a = n.stateNode, !(n.flags & 128) && (typeof t.getDerivedStateFromError == "function" || a !== null && typeof a.componentDidCatch == "function" && (tu === null || !tu.has(a)))) return n.flags |= 65536, i &= -i, n.lanes |= i, i = Ks(i), qs(i, e, n, r), La(n, i), !1;
			}
			n = n.return;
		} while (n !== null);
		return !1;
	}
	var Ys = Error(s(461)), Xs = !1;
	function Zs(e, t, n, r) {
		t.child = e === null ? Aa(t, null, n, r) : ka(t, e.child, n, r);
	}
	function Qs(e, t, n, r, i) {
		n = n.render;
		var a = t.ref;
		if ("ref" in r) {
			var o = {};
			for (var s in r) s !== "ref" && (o[s] = r[s]);
		} else o = r;
		return Gi(t), r = ho(e, t, n, o, a, i), s = yo(), e !== null && !Xs ? (bo(e, t, i), Sc(e, t, i)) : (Ti && s && bi(t), t.flags |= 1, Zs(e, t, r, i), t.child);
	}
	function $s(e, t, n, r, i) {
		if (e === null) {
			var a = n.type;
			return typeof a == "function" && !$r(a) && a.defaultProps === void 0 && n.compare === null ? (t.tag = 15, t.type = a, ec(e, t, a, r, i)) : (e = ni(n.type, null, r, t, t.mode, i), e.ref = t.ref, e.return = t, t.child = e);
		}
		if (a = e.child, !Cc(e, i)) {
			var o = a.memoizedProps;
			if (n = n.compare, n = n === null ? pr : n, n(o, r) && e.ref === t.ref) return Sc(e, t, i);
		}
		return t.flags |= 1, e = ei(a, r), e.ref = t.ref, e.return = t, t.child = e;
	}
	function ec(e, t, n, r, i) {
		if (e !== null) {
			var a = e.memoizedProps;
			if (pr(a, r) && e.ref === t.ref) if (Xs = !1, t.pendingProps = r = a, Cc(e, i)) e.flags & 131072 && (Xs = !0);
			else return t.lanes = e.lanes, Sc(e, t, i);
		}
		return cc(e, t, n, r, i);
	}
	function tc(e, t, n, r) {
		var i = r.children, a = e === null ? null : e.memoizedState;
		if (e === null && t.stateNode === null && (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), r.mode === "hidden") {
			if (t.flags & 128) {
				if (a = a === null ? n : a.baseLanes | n, e !== null) {
					for (r = t.child = e.child, i = 0; r !== null;) i = i | r.lanes | r.childLanes, r = r.sibling;
					r = i & ~a;
				} else r = 0, t.child = null;
				return rc(e, t, a, n, r);
			}
			if (n & 536870912) t.memoizedState = {
				baseLanes: 0,
				cachePool: null
			}, e !== null && da(t, a === null ? null : a.cachePool), a === null ? Ka() : Ga(t, a), Qa(t);
			else return r = t.lanes = 536870912, rc(e, t, a === null ? n : a.baseLanes | n, n, r);
		} else a === null ? (e !== null && da(t, null), Ka(), $a(t)) : (da(t, a.cachePool), Ga(t, a), $a(t), t.memoizedState = null);
		return Zs(e, t, i, n), t.child;
	}
	function nc(e, t) {
		return e !== null && e.tag === 22 || t.stateNode !== null || (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), t.sibling;
	}
	function rc(e, t, n, r, i) {
		var a = ua();
		return a = a === null ? null : {
			parent: Qi._currentValue,
			pool: a
		}, t.memoizedState = {
			baseLanes: n,
			cachePool: a
		}, e !== null && da(t, null), Ka(), Qa(t), e !== null && Ui(e, t, r, !0), t.childLanes = i, null;
	}
	function ic(e, t) {
		return t = _c({
			mode: t.mode,
			children: t.children
		}, e.mode), t.ref = e.ref, e.child = t, t.return = e, t;
	}
	function ac(e, t, n) {
		return ka(t, e.child, null, n), e = ic(t, t.pendingProps), e.flags |= 2, eo(t), t.memoizedState = null, e;
	}
	function oc(e, t, n) {
		var r = t.pendingProps, i = !!(t.flags & 128);
		if (t.flags &= -129, e === null) {
			if (Ti) {
				if (r.mode === "hidden") return e = ic(t, r), t.lanes = 536870912, nc(null, e);
				if (Za(t), (e = wi) ? (e = rf(e, Di), e = e !== null && e.data === "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: hi === null ? null : {
						id: gi,
						overflow: _i
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = ai(e), n.return = t, t.child = n, Ci = t, wi = null)) : e = null, e === null) throw ki(t);
				return t.lanes = 536870912, null;
			}
			return ic(t, r);
		}
		var a = e.memoizedState;
		if (a !== null) {
			var o = a.dehydrated;
			if (Za(t), i) if (t.flags & 256) t.flags &= -257, t = ac(e, t, n);
			else if (t.memoizedState !== null) t.child = e.child, t.flags |= 128, t = null;
			else throw Error(s(558));
			else if (Xs || Ui(e, t, n, !1), i = (n & e.childLanes) !== 0, Xs || i) {
				if (r = Fl, r !== null && (o = Ge(r, n), o !== 0 && o !== a.retryLane)) throw a.retryLane = o, qr(e, o), pu(r, e, o), Ys;
				Tu(), t = ac(e, t, n);
			} else e = a.treeContext, wi = cf(o.nextSibling), Ci = t, Ti = !0, Ei = null, Di = !1, e !== null && Si(t, e), t = ic(t, r), t.flags |= 4096;
			return t;
		}
		return e = ei(e.child, {
			mode: r.mode,
			children: r.children
		}), e.ref = t.ref, t.child = e, e.return = t, e;
	}
	function sc(e, t) {
		var n = t.ref;
		if (n === null) e !== null && e.ref !== null && (t.flags |= 4194816);
		else {
			if (typeof n != "function" && typeof n != "object") throw Error(s(284));
			(e === null || e.ref !== n) && (t.flags |= 4194816);
		}
	}
	function cc(e, t, n, r, i) {
		return Gi(t), n = ho(e, t, n, r, void 0, i), r = yo(), e !== null && !Xs ? (bo(e, t, i), Sc(e, t, i)) : (Ti && r && bi(t), t.flags |= 1, Zs(e, t, n, i), t.child);
	}
	function lc(e, t, n, r, i, a) {
		return Gi(t), t.updateQueue = null, n = _o(t, r, n, i), go(e), r = yo(), e !== null && !Xs ? (bo(e, t, a), Sc(e, t, a)) : (Ti && r && bi(t), t.flags |= 1, Zs(e, t, n, a), t.child);
	}
	function uc(e, t, n, r, i) {
		if (Gi(t), t.stateNode === null) {
			var a = Xr, o = n.contextType;
			typeof o == "object" && o && (a = Ki(o)), a = new n(r, a), t.memoizedState = a.state !== null && a.state !== void 0 ? a.state : null, a.updater = Is, t.stateNode = a, a._reactInternals = t, a = t.stateNode, a.props = r, a.state = t.memoizedState, a.refs = {}, Ma(t), o = n.contextType, a.context = typeof o == "object" && o ? Ki(o) : Xr, a.state = t.memoizedState, o = n.getDerivedStateFromProps, typeof o == "function" && (Fs(t, n, o, r), a.state = t.memoizedState), typeof n.getDerivedStateFromProps == "function" || typeof a.getSnapshotBeforeUpdate == "function" || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (o = a.state, typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount(), o !== a.state && Is.enqueueReplaceState(a, a.state, null), Ba(t, r, a, i), za(), a.state = t.memoizedState), typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !0;
		} else if (e === null) {
			a = t.stateNode;
			var s = t.memoizedProps, c = zs(n, s);
			a.props = c;
			var l = a.context, u = n.contextType;
			o = Xr, typeof u == "object" && u && (o = Ki(u));
			var d = n.getDerivedStateFromProps;
			u = typeof d == "function" || typeof a.getSnapshotBeforeUpdate == "function", s = t.pendingProps !== s, u || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (s || l !== o) && Rs(t, a, r, o), ja = !1;
			var f = t.memoizedState;
			a.state = f, Ba(t, r, a, i), za(), l = t.memoizedState, s || f !== l || ja ? (typeof d == "function" && (Fs(t, n, d, r), l = t.memoizedState), (c = ja || Ls(t, n, c, r, f, l, o)) ? (u || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount()), typeof a.componentDidMount == "function" && (t.flags |= 4194308)) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), t.memoizedProps = r, t.memoizedState = l), a.props = r, a.state = l, a.context = o, r = c) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !1);
		} else {
			a = t.stateNode, Na(e, t), o = t.memoizedProps, u = zs(n, o), a.props = u, d = t.pendingProps, f = a.context, l = n.contextType, c = Xr, typeof l == "object" && l && (c = Ki(l)), s = n.getDerivedStateFromProps, (l = typeof s == "function" || typeof a.getSnapshotBeforeUpdate == "function") || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (o !== d || f !== c) && Rs(t, a, r, c), ja = !1, f = t.memoizedState, a.state = f, Ba(t, r, a, i), za();
			var p = t.memoizedState;
			o !== d || f !== p || ja || e !== null && e.dependencies !== null && Wi(e.dependencies) ? (typeof s == "function" && (Fs(t, n, s, r), p = t.memoizedState), (u = ja || Ls(t, n, u, r, f, p, c) || e !== null && e.dependencies !== null && Wi(e.dependencies)) ? (l || typeof a.UNSAFE_componentWillUpdate != "function" && typeof a.componentWillUpdate != "function" || (typeof a.componentWillUpdate == "function" && a.componentWillUpdate(r, p, c), typeof a.UNSAFE_componentWillUpdate == "function" && a.UNSAFE_componentWillUpdate(r, p, c)), typeof a.componentDidUpdate == "function" && (t.flags |= 4), typeof a.getSnapshotBeforeUpdate == "function" && (t.flags |= 1024)) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), t.memoizedProps = r, t.memoizedState = p), a.props = r, a.state = p, a.context = c, r = u) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), r = !1);
		}
		return a = r, sc(e, t), r = !!(t.flags & 128), a || r ? (a = t.stateNode, n = r && typeof n.getDerivedStateFromError != "function" ? null : a.render(), t.flags |= 1, e !== null && r ? (t.child = ka(t, e.child, null, i), t.child = ka(t, null, n, i)) : Zs(e, t, n, i), t.memoizedState = a.state, e = t.child) : e = Sc(e, t, i), e;
	}
	function dc(e, t, n, r) {
		return Ni(), t.flags |= 256, Zs(e, t, n, r), t.child;
	}
	var fc = {
		dehydrated: null,
		treeContext: null,
		retryLane: 0,
		hydrationErrors: null
	};
	function pc(e) {
		return {
			baseLanes: e,
			cachePool: fa()
		};
	}
	function mc(e, t, n) {
		return e = e === null ? 0 : e.childLanes & ~n, t && (e |= Kl), e;
	}
	function hc(e, t, n) {
		var r = t.pendingProps, i = !1, a = !!(t.flags & 128), o;
		if ((o = a) || (o = e !== null && e.memoizedState === null ? !1 : !!(to.current & 2)), o && (i = !0, t.flags &= -129), o = !!(t.flags & 32), t.flags &= -33, e === null) {
			if (Ti) {
				if (i ? Xa(t) : $a(t), (e = wi) ? (e = rf(e, Di), e = e !== null && e.data !== "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: hi === null ? null : {
						id: gi,
						overflow: _i
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = ai(e), n.return = t, t.child = n, Ci = t, wi = null)) : e = null, e === null) throw ki(t);
				return of(e) ? t.lanes = 32 : t.lanes = 536870912, null;
			}
			var c = r.children;
			return r = r.fallback, i ? ($a(t), i = t.mode, c = _c({
				mode: "hidden",
				children: c
			}, i), r = ri(r, i, n, null), c.return = t, r.return = t, c.sibling = r, t.child = c, r = t.child, r.memoizedState = pc(n), r.childLanes = mc(e, o, n), t.memoizedState = fc, nc(null, r)) : (Xa(t), gc(t, c));
		}
		var l = e.memoizedState;
		if (l !== null && (c = l.dehydrated, c !== null)) {
			if (a) t.flags & 256 ? (Xa(t), t.flags &= -257, t = vc(e, t, n)) : t.memoizedState === null ? ($a(t), c = r.fallback, i = t.mode, r = _c({
				mode: "visible",
				children: r.children
			}, i), c = ri(c, i, n, null), c.flags |= 2, r.return = t, c.return = t, r.sibling = c, t.child = r, ka(t, e.child, null, n), r = t.child, r.memoizedState = pc(n), r.childLanes = mc(e, o, n), t.memoizedState = fc, t = nc(null, r)) : ($a(t), t.child = e.child, t.flags |= 128, t = null);
			else if (Xa(t), of(c)) {
				if (o = c.nextSibling && c.nextSibling.dataset, o) var u = o.dgst;
				o = u, r = Error(s(419)), r.stack = "", r.digest = o, Fi({
					value: r,
					source: null,
					stack: null
				}), t = vc(e, t, n);
			} else if (Xs || Ui(e, t, n, !1), o = (n & e.childLanes) !== 0, Xs || o) {
				if (o = Fl, o !== null && (r = Ge(o, n), r !== 0 && r !== l.retryLane)) throw l.retryLane = r, qr(e, r), pu(o, e, r), Ys;
				af(c) || Tu(), t = vc(e, t, n);
			} else af(c) ? (t.flags |= 192, t.child = e.child, t = null) : (e = l.treeContext, wi = cf(c.nextSibling), Ci = t, Ti = !0, Ei = null, Di = !1, e !== null && Si(t, e), t = gc(t, r.children), t.flags |= 4096);
			return t;
		}
		return i ? ($a(t), c = r.fallback, i = t.mode, l = e.child, u = l.sibling, r = ei(l, {
			mode: "hidden",
			children: r.children
		}), r.subtreeFlags = l.subtreeFlags & 65011712, u === null ? (c = ri(c, i, n, null), c.flags |= 2) : c = ei(u, c), c.return = t, r.return = t, r.sibling = c, t.child = r, nc(null, r), r = t.child, c = e.child.memoizedState, c === null ? c = pc(n) : (i = c.cachePool, i === null ? i = fa() : (l = Qi._currentValue, i = i.parent === l ? i : {
			parent: l,
			pool: l
		}), c = {
			baseLanes: c.baseLanes | n,
			cachePool: i
		}), r.memoizedState = c, r.childLanes = mc(e, o, n), t.memoizedState = fc, nc(e.child, r)) : (Xa(t), n = e.child, e = n.sibling, n = ei(n, {
			mode: "visible",
			children: r.children
		}), n.return = t, n.sibling = null, e !== null && (o = t.deletions, o === null ? (t.deletions = [e], t.flags |= 16) : o.push(e)), t.child = n, t.memoizedState = null, n);
	}
	function gc(e, t) {
		return t = _c({
			mode: "visible",
			children: t
		}, e.mode), t.return = e, e.child = t;
	}
	function _c(e, t) {
		return e = Qr(22, e, null, t), e.lanes = 0, e;
	}
	function vc(e, t, n) {
		return ka(t, e.child, null, n), e = gc(t, t.pendingProps.children), e.flags |= 2, t.memoizedState = null, e;
	}
	function yc(e, t, n) {
		e.lanes |= t;
		var r = e.alternate;
		r !== null && (r.lanes |= t), Vi(e.return, t, n);
	}
	function bc(e, t, n, r, i, a) {
		var o = e.memoizedState;
		o === null ? e.memoizedState = {
			isBackwards: t,
			rendering: null,
			renderingStartTime: 0,
			last: r,
			tail: n,
			tailMode: i,
			treeForkCount: a
		} : (o.isBackwards = t, o.rendering = null, o.renderingStartTime = 0, o.last = r, o.tail = n, o.tailMode = i, o.treeForkCount = a);
	}
	function xc(e, t, n) {
		var r = t.pendingProps, i = r.revealOrder, a = r.tail;
		r = r.children;
		var o = to.current, s = !!(o & 2);
		if (s ? (o = o & 1 | 2, t.flags |= 128) : o &= 1, U(to, o), Zs(e, t, r, n), r = Ti ? fi : 0, !s && e !== null && e.flags & 128) a: for (e = t.child; e !== null;) {
			if (e.tag === 13) e.memoizedState !== null && yc(e, n, t);
			else if (e.tag === 19) yc(e, n, t);
			else if (e.child !== null) {
				e.child.return = e, e = e.child;
				continue;
			}
			if (e === t) break a;
			for (; e.sibling === null;) {
				if (e.return === null || e.return === t) break a;
				e = e.return;
			}
			e.sibling.return = e.return, e = e.sibling;
		}
		switch (i) {
			case "forwards":
				for (n = t.child, i = null; n !== null;) e = n.alternate, e !== null && no(e) === null && (i = n), n = n.sibling;
				n = i, n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null), bc(t, !1, i, n, a, r);
				break;
			case "backwards":
			case "unstable_legacy-backwards":
				for (n = null, i = t.child, t.child = null; i !== null;) {
					if (e = i.alternate, e !== null && no(e) === null) {
						t.child = i;
						break;
					}
					e = i.sibling, i.sibling = n, n = i, i = e;
				}
				bc(t, !0, n, null, a, r);
				break;
			case "together":
				bc(t, !1, null, null, void 0, r);
				break;
			default: t.memoizedState = null;
		}
		return t.child;
	}
	function Sc(e, t, n) {
		if (e !== null && (t.dependencies = e.dependencies), Ul |= t.lanes, (n & t.childLanes) === 0) if (e !== null) {
			if (Ui(e, t, n, !1), (n & t.childLanes) === 0) return null;
		} else return null;
		if (e !== null && t.child !== e.child) throw Error(s(153));
		if (t.child !== null) {
			for (e = t.child, n = ei(e, e.pendingProps), t.child = n, n.return = t; e.sibling !== null;) e = e.sibling, n = n.sibling = ei(e, e.pendingProps), n.return = t;
			n.sibling = null;
		}
		return t.child;
	}
	function Cc(e, t) {
		return (e.lanes & t) !== 0 || (e = e.dependencies, !!(e !== null && Wi(e)));
	}
	function wc(e, t, n) {
		switch (t.tag) {
			case 3:
				K(t, t.stateNode.containerInfo), zi(t, Qi, e.memoizedState.cache), Ni();
				break;
			case 27:
			case 5:
				ne(t);
				break;
			case 4:
				K(t, t.stateNode.containerInfo);
				break;
			case 10:
				zi(t, t.type, t.memoizedProps.value);
				break;
			case 31:
				if (t.memoizedState !== null) return t.flags |= 128, Za(t), null;
				break;
			case 13:
				var r = t.memoizedState;
				if (r !== null) return r.dehydrated === null ? (n & t.child.childLanes) === 0 ? (Xa(t), e = Sc(e, t, n), e === null ? null : e.sibling) : hc(e, t, n) : (Xa(t), t.flags |= 128, null);
				Xa(t);
				break;
			case 19:
				var i = !!(e.flags & 128);
				if (r = (n & t.childLanes) !== 0, r ||= (Ui(e, t, n, !1), (n & t.childLanes) !== 0), i) {
					if (r) return xc(e, t, n);
					t.flags |= 128;
				}
				if (i = t.memoizedState, i !== null && (i.rendering = null, i.tail = null, i.lastEffect = null), U(to, to.current), r) break;
				return null;
			case 22: return t.lanes = 0, tc(e, t, n, t.pendingProps);
			case 24: zi(t, Qi, e.memoizedState.cache);
		}
		return Sc(e, t, n);
	}
	function Tc(e, t, n) {
		if (e !== null) if (e.memoizedProps !== t.pendingProps) Xs = !0;
		else {
			if (!Cc(e, n) && !(t.flags & 128)) return Xs = !1, wc(e, t, n);
			Xs = !!(e.flags & 131072);
		}
		else Xs = !1, Ti && t.flags & 1048576 && yi(t, fi, t.index);
		switch (t.lanes = 0, t.tag) {
			case 16:
				a: {
					var r = t.pendingProps;
					if (e = ya(t.elementType), t.type = e, typeof e == "function") $r(e) ? (r = zs(e, r), t.tag = 1, t = uc(null, t, e, r, n)) : (t.tag = 0, t = cc(null, t, e, r, n));
					else {
						if (e != null) {
							var i = e.$$typeof;
							if (i === w) {
								t.tag = 11, t = Qs(null, t, e, r, n);
								break a;
							}
							if (i === D) {
								t.tag = 14, t = $s(null, t, e, r, n);
								break a;
							}
						}
						throw t = P(e) || e, Error(s(306, t, ""));
					}
				}
				return t;
			case 0: return cc(e, t, t.type, t.pendingProps, n);
			case 1: return r = t.type, i = zs(r, t.pendingProps), uc(e, t, r, i, n);
			case 3:
				a: {
					if (K(t, t.stateNode.containerInfo), e === null) throw Error(s(387));
					r = t.pendingProps;
					var a = t.memoizedState;
					i = a.element, Na(e, t), Ba(t, r, null, n);
					var o = t.memoizedState;
					if (r = o.cache, zi(t, Qi, r), r !== a.cache && Hi(t, [Qi], n, !0), za(), r = o.element, a.isDehydrated) if (a = {
						element: r,
						isDehydrated: !1,
						cache: o.cache
					}, t.updateQueue.baseState = a, t.memoizedState = a, t.flags & 256) {
						t = dc(e, t, r, n);
						break a;
					} else if (r !== i) {
						i = ci(Error(s(424)), t), Fi(i), t = dc(e, t, r, n);
						break a;
					} else {
						switch (e = t.stateNode.containerInfo, e.nodeType) {
							case 9:
								e = e.body;
								break;
							default: e = e.nodeName === "HTML" ? e.ownerDocument.body : e;
						}
						for (wi = cf(e.firstChild), Ci = t, Ti = !0, Ei = null, Di = !0, n = Aa(t, null, r, n), t.child = n; n;) n.flags = n.flags & -3 | 4096, n = n.sibling;
					}
					else {
						if (Ni(), r === i) {
							t = Sc(e, t, n);
							break a;
						}
						Zs(e, t, r, n);
					}
					t = t.child;
				}
				return t;
			case 26: return sc(e, t), e === null ? (n = kf(t.type, null, t.pendingProps, null)) ? t.memoizedState = n : Ti || (n = t.type, e = t.pendingProps, r = Bd(W.current).createElement(n), r[Ze] = t, r[Qe] = e, Pd(r, n, e), ut(r), t.stateNode = r) : t.memoizedState = kf(t.type, e.memoizedProps, t.pendingProps, e.memoizedState), null;
			case 27: return ne(t), e === null && Ti && (r = t.stateNode = ff(t.type, t.pendingProps, W.current), Ci = t, Di = !0, i = wi, Zd(t.type) ? (lf = i, wi = cf(r.firstChild)) : wi = i), Zs(e, t, t.pendingProps.children, n), sc(e, t), e === null && (t.flags |= 4194304), t.child;
			case 5: return e === null && Ti && ((i = r = wi) && (r = tf(r, t.type, t.pendingProps, Di), r === null ? i = !1 : (t.stateNode = r, Ci = t, wi = cf(r.firstChild), Di = !1, i = !0)), i || ki(t)), ne(t), i = t.type, a = t.pendingProps, o = e === null ? null : e.memoizedProps, r = a.children, Ud(i, a) ? r = null : o !== null && Ud(i, o) && (t.flags |= 32), t.memoizedState !== null && (i = ho(e, t, vo, null, null, n), Qf._currentValue = i), sc(e, t), Zs(e, t, r, n), t.child;
			case 6: return e === null && Ti && ((e = n = wi) && (n = nf(n, t.pendingProps, Di), n === null ? e = !1 : (t.stateNode = n, Ci = t, wi = null, e = !0)), e || ki(t)), null;
			case 13: return hc(e, t, n);
			case 4: return K(t, t.stateNode.containerInfo), r = t.pendingProps, e === null ? t.child = ka(t, null, r, n) : Zs(e, t, r, n), t.child;
			case 11: return Qs(e, t, t.type, t.pendingProps, n);
			case 7: return Zs(e, t, t.pendingProps, n), t.child;
			case 8: return Zs(e, t, t.pendingProps.children, n), t.child;
			case 12: return Zs(e, t, t.pendingProps.children, n), t.child;
			case 10: return r = t.pendingProps, zi(t, t.type, r.value), Zs(e, t, r.children, n), t.child;
			case 9: return i = t.type._context, r = t.pendingProps.children, Gi(t), i = Ki(i), r = r(i), t.flags |= 1, Zs(e, t, r, n), t.child;
			case 14: return $s(e, t, t.type, t.pendingProps, n);
			case 15: return ec(e, t, t.type, t.pendingProps, n);
			case 19: return xc(e, t, n);
			case 31: return oc(e, t, n);
			case 22: return tc(e, t, n, t.pendingProps);
			case 24: return Gi(t), r = Ki(Qi), e === null ? (i = ua(), i === null && (i = Fl, a = $i(), i.pooledCache = a, a.refCount++, a !== null && (i.pooledCacheLanes |= n), i = a), t.memoizedState = {
				parent: r,
				cache: i
			}, Ma(t), zi(t, Qi, i)) : ((e.lanes & n) !== 0 && (Na(e, t), Ba(t, null, null, n), za()), i = e.memoizedState, a = t.memoizedState, i.parent === r ? (r = a.cache, zi(t, Qi, r), r !== i.cache && Hi(t, [Qi], n, !0)) : (i = {
				parent: r,
				cache: r
			}, t.memoizedState = i, t.lanes === 0 && (t.memoizedState = t.updateQueue.baseState = i), zi(t, Qi, r))), Zs(e, t, t.pendingProps.children, n), t.child;
			case 29: throw t.pendingProps;
		}
		throw Error(s(156, t.tag));
	}
	function Ec(e) {
		e.flags |= 4;
	}
	function Dc(e, t, n, r, i) {
		if ((t = !!(e.mode & 32)) && (t = !1), t) {
			if (e.flags |= 16777216, (i & 335544128) === i) if (e.stateNode.complete) e.flags |= 8192;
			else if (Su()) e.flags |= 8192;
			else throw ba = ga, ma;
		} else e.flags &= -16777217;
	}
	function Oc(e, t) {
		if (t.type !== "stylesheet" || t.state.loading & 4) e.flags &= -16777217;
		else if (e.flags |= 16777216, !Wf(t)) if (Su()) e.flags |= 8192;
		else throw ba = ga, ma;
	}
	function kc(e, t) {
		t !== null && (e.flags |= 4), e.flags & 16384 && (t = e.tag === 22 ? 536870912 : ze(), e.lanes |= t, ql |= t);
	}
	function Ac(e, t) {
		if (!Ti) switch (e.tailMode) {
			case "hidden":
				t = e.tail;
				for (var n = null; t !== null;) t.alternate !== null && (n = t), t = t.sibling;
				n === null ? e.tail = null : n.sibling = null;
				break;
			case "collapsed":
				n = e.tail;
				for (var r = null; n !== null;) n.alternate !== null && (r = n), n = n.sibling;
				r === null ? t || e.tail === null ? e.tail = null : e.tail.sibling = null : r.sibling = null;
		}
	}
	function jc(e) {
		var t = e.alternate !== null && e.alternate.child === e.child, n = 0, r = 0;
		if (t) for (var i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags & 65011712, r |= i.flags & 65011712, i.return = e, i = i.sibling;
		else for (i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags, r |= i.flags, i.return = e, i = i.sibling;
		return e.subtreeFlags |= r, e.childLanes = n, t;
	}
	function Mc(e, t, n) {
		var r = t.pendingProps;
		switch (xi(t), t.tag) {
			case 16:
			case 15:
			case 0:
			case 11:
			case 7:
			case 8:
			case 12:
			case 9:
			case 14: return jc(t), null;
			case 1: return jc(t), null;
			case 3: return n = t.stateNode, r = null, e !== null && (r = e.memoizedState.cache), t.memoizedState.cache !== r && (t.flags |= 2048), Bi(Qi), q(), n.pendingContext && (n.context = n.pendingContext, n.pendingContext = null), (e === null || e.child === null) && (Mi(t) ? Ec(t) : e === null || e.memoizedState.isDehydrated && !(t.flags & 256) || (t.flags |= 1024, Pi())), jc(t), null;
			case 26:
				var i = t.type, a = t.memoizedState;
				return e === null ? (Ec(t), a === null ? (jc(t), Dc(t, i, null, r, n)) : (jc(t), Oc(t, a))) : a ? a === e.memoizedState ? (jc(t), t.flags &= -16777217) : (Ec(t), jc(t), Oc(t, a)) : (e = e.memoizedProps, e !== r && Ec(t), jc(t), Dc(t, i, e, r, n)), null;
			case 27:
				if (re(t), n = W.current, i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && Ec(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return jc(t), null;
					}
					e = ee.current, Mi(t) ? Ai(t, e) : (e = ff(i, r, n), t.stateNode = e, Ec(t));
				}
				return jc(t), null;
			case 5:
				if (re(t), i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && Ec(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return jc(t), null;
					}
					if (a = ee.current, Mi(t)) Ai(t, a);
					else {
						var o = Bd(W.current);
						switch (a) {
							case 1:
								a = o.createElementNS("http://www.w3.org/2000/svg", i);
								break;
							case 2:
								a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
								break;
							default: switch (i) {
								case "svg":
									a = o.createElementNS("http://www.w3.org/2000/svg", i);
									break;
								case "math":
									a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
									break;
								case "script":
									a = o.createElement("div"), a.innerHTML = "<script><\/script>", a = a.removeChild(a.firstChild);
									break;
								case "select":
									a = typeof r.is == "string" ? o.createElement("select", { is: r.is }) : o.createElement("select"), r.multiple ? a.multiple = !0 : r.size && (a.size = r.size);
									break;
								default: a = typeof r.is == "string" ? o.createElement(i, { is: r.is }) : o.createElement(i);
							}
						}
						a[Ze] = t, a[Qe] = r;
						a: for (o = t.child; o !== null;) {
							if (o.tag === 5 || o.tag === 6) a.appendChild(o.stateNode);
							else if (o.tag !== 4 && o.tag !== 27 && o.child !== null) {
								o.child.return = o, o = o.child;
								continue;
							}
							if (o === t) break a;
							for (; o.sibling === null;) {
								if (o.return === null || o.return === t) break a;
								o = o.return;
							}
							o.sibling.return = o.return, o = o.sibling;
						}
						t.stateNode = a;
						a: switch (Pd(a, i, r), i) {
							case "button":
							case "input":
							case "select":
							case "textarea":
								r = !!r.autoFocus;
								break a;
							case "img":
								r = !0;
								break a;
							default: r = !1;
						}
						r && Ec(t);
					}
				}
				return jc(t), Dc(t, t.type, e === null ? null : e.memoizedProps, t.pendingProps, n), null;
			case 6:
				if (e && t.stateNode != null) e.memoizedProps !== r && Ec(t);
				else {
					if (typeof r != "string" && t.stateNode === null) throw Error(s(166));
					if (e = W.current, Mi(t)) {
						if (e = t.stateNode, n = t.memoizedProps, r = null, i = Ci, i !== null) switch (i.tag) {
							case 27:
							case 5: r = i.memoizedProps;
						}
						e[Ze] = t, e = !!(e.nodeValue === n || r !== null && !0 === r.suppressHydrationWarning || jd(e.nodeValue, n)), e || ki(t, !0);
					} else e = Bd(e).createTextNode(r), e[Ze] = t, t.stateNode = e;
				}
				return jc(t), null;
			case 31:
				if (n = t.memoizedState, e === null || e.memoizedState !== null) {
					if (r = Mi(t), n !== null) {
						if (e === null) {
							if (!r) throw Error(s(318));
							if (e = t.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(557));
							e[Ze] = t;
						} else Ni(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						jc(t), e = !1;
					} else n = Pi(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = n), e = !0;
					if (!e) return t.flags & 256 ? (eo(t), t) : (eo(t), null);
					if (t.flags & 128) throw Error(s(558));
				}
				return jc(t), null;
			case 13:
				if (r = t.memoizedState, e === null || e.memoizedState !== null && e.memoizedState.dehydrated !== null) {
					if (i = Mi(t), r !== null && r.dehydrated !== null) {
						if (e === null) {
							if (!i) throw Error(s(318));
							if (i = t.memoizedState, i = i === null ? null : i.dehydrated, !i) throw Error(s(317));
							i[Ze] = t;
						} else Ni(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						jc(t), i = !1;
					} else i = Pi(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = i), i = !0;
					if (!i) return t.flags & 256 ? (eo(t), t) : (eo(t), null);
				}
				return eo(t), t.flags & 128 ? (t.lanes = n, t) : (n = r !== null, e = e !== null && e.memoizedState !== null, n && (r = t.child, i = null, r.alternate !== null && r.alternate.memoizedState !== null && r.alternate.memoizedState.cachePool !== null && (i = r.alternate.memoizedState.cachePool.pool), a = null, r.memoizedState !== null && r.memoizedState.cachePool !== null && (a = r.memoizedState.cachePool.pool), a !== i && (r.flags |= 2048)), n !== e && n && (t.child.flags |= 8192), kc(t, t.updateQueue), jc(t), null);
			case 4: return q(), e === null && xd(t.stateNode.containerInfo), jc(t), null;
			case 10: return Bi(t.type), jc(t), null;
			case 19:
				if (H(to), r = t.memoizedState, r === null) return jc(t), null;
				if (i = !!(t.flags & 128), a = r.rendering, a === null) if (i) Ac(r, !1);
				else {
					if (Hl !== 0 || e !== null && e.flags & 128) for (e = t.child; e !== null;) {
						if (a = no(e), a !== null) {
							for (t.flags |= 128, Ac(r, !1), e = a.updateQueue, t.updateQueue = e, kc(t, e), t.subtreeFlags = 0, e = n, n = t.child; n !== null;) ti(n, e), n = n.sibling;
							return U(to, to.current & 1 | 2), Ti && vi(t, r.treeForkCount), t.child;
						}
						e = e.sibling;
					}
					r.tail !== null && ge() > $l && (t.flags |= 128, i = !0, Ac(r, !1), t.lanes = 4194304);
				}
				else {
					if (!i) if (e = no(a), e !== null) {
						if (t.flags |= 128, i = !0, e = e.updateQueue, t.updateQueue = e, kc(t, e), Ac(r, !0), r.tail === null && r.tailMode === "hidden" && !a.alternate && !Ti) return jc(t), null;
					} else 2 * ge() - r.renderingStartTime > $l && n !== 536870912 && (t.flags |= 128, i = !0, Ac(r, !1), t.lanes = 4194304);
					r.isBackwards ? (a.sibling = t.child, t.child = a) : (e = r.last, e === null ? t.child = a : e.sibling = a, r.last = a);
				}
				return r.tail === null ? (jc(t), null) : (e = r.tail, r.rendering = e, r.tail = e.sibling, r.renderingStartTime = ge(), e.sibling = null, n = to.current, U(to, i ? n & 1 | 2 : n & 1), Ti && vi(t, r.treeForkCount), e);
			case 22:
			case 23: return eo(t), qa(), r = t.memoizedState !== null, e === null ? r && (t.flags |= 8192) : e.memoizedState !== null !== r && (t.flags |= 8192), r ? n & 536870912 && !(t.flags & 128) && (jc(t), t.subtreeFlags & 6 && (t.flags |= 8192)) : jc(t), n = t.updateQueue, n !== null && kc(t, n.retryQueue), n = null, e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), r = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (r = t.memoizedState.cachePool.pool), r !== n && (t.flags |= 2048), e !== null && H(la), null;
			case 24: return n = null, e !== null && (n = e.memoizedState.cache), t.memoizedState.cache !== n && (t.flags |= 2048), Bi(Qi), jc(t), null;
			case 25: return null;
			case 30: return null;
		}
		throw Error(s(156, t.tag));
	}
	function Nc(e, t) {
		switch (xi(t), t.tag) {
			case 1: return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 3: return Bi(Qi), q(), e = t.flags, e & 65536 && !(e & 128) ? (t.flags = e & -65537 | 128, t) : null;
			case 26:
			case 27:
			case 5: return re(t), null;
			case 31:
				if (t.memoizedState !== null) {
					if (eo(t), t.alternate === null) throw Error(s(340));
					Ni();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 13:
				if (eo(t), e = t.memoizedState, e !== null && e.dehydrated !== null) {
					if (t.alternate === null) throw Error(s(340));
					Ni();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 19: return H(to), null;
			case 4: return q(), null;
			case 10: return Bi(t.type), null;
			case 22:
			case 23: return eo(t), qa(), e !== null && H(la), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 24: return Bi(Qi), null;
			case 25: return null;
			default: return null;
		}
	}
	function Pc(e, t) {
		switch (xi(t), t.tag) {
			case 3:
				Bi(Qi), q();
				break;
			case 26:
			case 27:
			case 5:
				re(t);
				break;
			case 4:
				q();
				break;
			case 31:
				t.memoizedState !== null && eo(t);
				break;
			case 13:
				eo(t);
				break;
			case 19:
				H(to);
				break;
			case 10:
				Bi(t.type);
				break;
			case 22:
			case 23:
				eo(t), qa(), e !== null && H(la);
				break;
			case 24: Bi(Qi);
		}
	}
	function Fc(e, t) {
		try {
			var n = t.updateQueue, r = n === null ? null : n.lastEffect;
			if (r !== null) {
				var i = r.next;
				n = i;
				do {
					if ((n.tag & e) === e) {
						r = void 0;
						var a = n.create, o = n.inst;
						r = a(), o.destroy = r;
					}
					n = n.next;
				} while (n !== i);
			}
		} catch (e) {
			Uu(t, t.return, e);
		}
	}
	function Ic(e, t, n) {
		try {
			var r = t.updateQueue, i = r === null ? null : r.lastEffect;
			if (i !== null) {
				var a = i.next;
				r = a;
				do {
					if ((r.tag & e) === e) {
						var o = r.inst, s = o.destroy;
						if (s !== void 0) {
							o.destroy = void 0, i = t;
							var c = n, l = s;
							try {
								l();
							} catch (e) {
								Uu(i, c, e);
							}
						}
					}
					r = r.next;
				} while (r !== a);
			}
		} catch (e) {
			Uu(t, t.return, e);
		}
	}
	function Lc(e) {
		var t = e.updateQueue;
		if (t !== null) {
			var n = e.stateNode;
			try {
				Ha(t, n);
			} catch (t) {
				Uu(e, e.return, t);
			}
		}
	}
	function Rc(e, t, n) {
		n.props = zs(e.type, e.memoizedProps), n.state = e.memoizedState;
		try {
			n.componentWillUnmount();
		} catch (n) {
			Uu(e, t, n);
		}
	}
	function zc(e, t) {
		try {
			var n = e.ref;
			if (n !== null) {
				switch (e.tag) {
					case 26:
					case 27:
					case 5:
						var r = e.stateNode;
						break;
					case 30:
						r = e.stateNode;
						break;
					default: r = e.stateNode;
				}
				typeof n == "function" ? e.refCleanup = n(r) : n.current = r;
			}
		} catch (n) {
			Uu(e, t, n);
		}
	}
	function Bc(e, t) {
		var n = e.ref, r = e.refCleanup;
		if (n !== null) if (typeof r == "function") try {
			r();
		} catch (n) {
			Uu(e, t, n);
		} finally {
			e.refCleanup = null, e = e.alternate, e != null && (e.refCleanup = null);
		}
		else if (typeof n == "function") try {
			n(null);
		} catch (n) {
			Uu(e, t, n);
		}
		else n.current = null;
	}
	function Vc(e) {
		var t = e.type, n = e.memoizedProps, r = e.stateNode;
		try {
			a: switch (t) {
				case "button":
				case "input":
				case "select":
				case "textarea":
					n.autoFocus && r.focus();
					break a;
				case "img": n.src ? r.src = n.src : n.srcSet && (r.srcset = n.srcSet);
			}
		} catch (t) {
			Uu(e, e.return, t);
		}
	}
	function Hc(e, t, n) {
		try {
			var r = e.stateNode;
			Fd(r, e.type, n, t), r[Qe] = t;
		} catch (t) {
			Uu(e, e.return, t);
		}
	}
	function Uc(e) {
		return e.tag === 5 || e.tag === 3 || e.tag === 26 || e.tag === 27 && Zd(e.type) || e.tag === 4;
	}
	function Wc(e) {
		a: for (;;) {
			for (; e.sibling === null;) {
				if (e.return === null || Uc(e.return)) return null;
				e = e.return;
			}
			for (e.sibling.return = e.return, e = e.sibling; e.tag !== 5 && e.tag !== 6 && e.tag !== 18;) {
				if (e.tag === 27 && Zd(e.type) || e.flags & 2 || e.child === null || e.tag === 4) continue a;
				e.child.return = e, e = e.child;
			}
			if (!(e.flags & 2)) return e.stateNode;
		}
	}
	function Gc(e, t, n) {
		var r = e.tag;
		if (r === 5 || r === 6) e = e.stateNode, t ? (n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n).insertBefore(e, t) : (t = n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n, t.appendChild(e), n = n._reactRootContainer, n != null || t.onclick !== null || (t.onclick = Wt));
		else if (r !== 4 && (r === 27 && Zd(e.type) && (n = e.stateNode, t = null), e = e.child, e !== null)) for (Gc(e, t, n), e = e.sibling; e !== null;) Gc(e, t, n), e = e.sibling;
	}
	function Kc(e, t, n) {
		var r = e.tag;
		if (r === 5 || r === 6) e = e.stateNode, t ? n.insertBefore(e, t) : n.appendChild(e);
		else if (r !== 4 && (r === 27 && Zd(e.type) && (n = e.stateNode), e = e.child, e !== null)) for (Kc(e, t, n), e = e.sibling; e !== null;) Kc(e, t, n), e = e.sibling;
	}
	function qc(e) {
		var t = e.stateNode, n = e.memoizedProps;
		try {
			for (var r = e.type, i = t.attributes; i.length;) t.removeAttributeNode(i[0]);
			Pd(t, r, n), t[Ze] = e, t[Qe] = n;
		} catch (t) {
			Uu(e, e.return, t);
		}
	}
	var Jc = !1, Yc = !1, Xc = !1, Zc = typeof WeakSet == "function" ? WeakSet : Set, Qc = null;
	function $c(e, t) {
		if (e = e.containerInfo, Rd = sp, e = _r(e), vr(e)) {
			if ("selectionStart" in e) var n = {
				start: e.selectionStart,
				end: e.selectionEnd
			};
			else a: {
				n = (n = e.ownerDocument) && n.defaultView || window;
				var r = n.getSelection && n.getSelection();
				if (r && r.rangeCount !== 0) {
					n = r.anchorNode;
					var i = r.anchorOffset, a = r.focusNode;
					r = r.focusOffset;
					try {
						n.nodeType, a.nodeType;
					} catch {
						n = null;
						break a;
					}
					var o = 0, c = -1, l = -1, u = 0, d = 0, f = e, p = null;
					b: for (;;) {
						for (var m; f !== n || i !== 0 && f.nodeType !== 3 || (c = o + i), f !== a || r !== 0 && f.nodeType !== 3 || (l = o + r), f.nodeType === 3 && (o += f.nodeValue.length), (m = f.firstChild) !== null;) p = f, f = m;
						for (;;) {
							if (f === e) break b;
							if (p === n && ++u === i && (c = o), p === a && ++d === r && (l = o), (m = f.nextSibling) !== null) break;
							f = p, p = f.parentNode;
						}
						f = m;
					}
					n = c === -1 || l === -1 ? null : {
						start: c,
						end: l
					};
				} else n = null;
			}
			n ||= {
				start: 0,
				end: 0
			};
		} else n = null;
		for (zd = {
			focusedElem: e,
			selectionRange: n
		}, sp = !1, Qc = t; Qc !== null;) if (t = Qc, e = t.child, t.subtreeFlags & 1028 && e !== null) e.return = t, Qc = e;
		else for (; Qc !== null;) {
			switch (t = Qc, a = t.alternate, e = t.flags, t.tag) {
				case 0:
					if (e & 4 && (e = t.updateQueue, e = e === null ? null : e.events, e !== null)) for (n = 0; n < e.length; n++) i = e[n], i.ref.impl = i.nextImpl;
					break;
				case 11:
				case 15: break;
				case 1:
					if (e & 1024 && a !== null) {
						e = void 0, n = t, i = a.memoizedProps, a = a.memoizedState, r = n.stateNode;
						try {
							var h = zs(n.type, i);
							e = r.getSnapshotBeforeUpdate(h, a), r.__reactInternalSnapshotBeforeUpdate = e;
						} catch (e) {
							Uu(n, n.return, e);
						}
					}
					break;
				case 3:
					if (e & 1024) {
						if (e = t.stateNode.containerInfo, n = e.nodeType, n === 9) ef(e);
						else if (n === 1) switch (e.nodeName) {
							case "HEAD":
							case "HTML":
							case "BODY":
								ef(e);
								break;
							default: e.textContent = "";
						}
					}
					break;
				case 5:
				case 26:
				case 27:
				case 6:
				case 4:
				case 17: break;
				default: if (e & 1024) throw Error(s(163));
			}
			if (e = t.sibling, e !== null) {
				e.return = t.return, Qc = e;
				break;
			}
			Qc = t.return;
		}
	}
	function el(e, t, n) {
		var r = n.flags;
		switch (n.tag) {
			case 0:
			case 11:
			case 15:
				hl(e, n), r & 4 && Fc(5, n);
				break;
			case 1:
				if (hl(e, n), r & 4) if (e = n.stateNode, t === null) try {
					e.componentDidMount();
				} catch (e) {
					Uu(n, n.return, e);
				}
				else {
					var i = zs(n.type, t.memoizedProps);
					t = t.memoizedState;
					try {
						e.componentDidUpdate(i, t, e.__reactInternalSnapshotBeforeUpdate);
					} catch (e) {
						Uu(n, n.return, e);
					}
				}
				r & 64 && Lc(n), r & 512 && zc(n, n.return);
				break;
			case 3:
				if (hl(e, n), r & 64 && (e = n.updateQueue, e !== null)) {
					if (t = null, n.child !== null) switch (n.child.tag) {
						case 27:
						case 5:
							t = n.child.stateNode;
							break;
						case 1: t = n.child.stateNode;
					}
					try {
						Ha(e, t);
					} catch (e) {
						Uu(n, n.return, e);
					}
				}
				break;
			case 27: t === null && r & 4 && qc(n);
			case 26:
			case 5:
				hl(e, n), t === null && r & 4 && Vc(n), r & 512 && zc(n, n.return);
				break;
			case 12:
				hl(e, n);
				break;
			case 31:
				hl(e, n), r & 4 && ol(e, n);
				break;
			case 13:
				hl(e, n), r & 4 && sl(e, n), r & 64 && (e = n.memoizedState, e !== null && (e = e.dehydrated, e !== null && (n = qu.bind(null, n), sf(e, n))));
				break;
			case 22:
				if (r = n.memoizedState !== null || Jc, !r) {
					t = t !== null && t.memoizedState !== null || Yc, i = Jc;
					var a = Yc;
					Jc = r, (Yc = t) && !a ? _l(e, n, !!(n.subtreeFlags & 8772)) : hl(e, n), Jc = i, Yc = a;
				}
				break;
			case 30: break;
			default: hl(e, n);
		}
	}
	function tl(e) {
		var t = e.alternate;
		t !== null && (e.alternate = null, tl(t)), e.child = null, e.deletions = null, e.sibling = null, e.tag === 5 && (t = e.stateNode, t !== null && at(t)), e.stateNode = null, e.return = null, e.dependencies = null, e.memoizedProps = null, e.memoizedState = null, e.pendingProps = null, e.stateNode = null, e.updateQueue = null;
	}
	var nl = null, rl = !1;
	function il(e, t, n) {
		for (n = n.child; n !== null;) al(e, t, n), n = n.sibling;
	}
	function al(e, t, n) {
		if (Ee && typeof Ee.onCommitFiberUnmount == "function") try {
			Ee.onCommitFiberUnmount(Te, n);
		} catch {}
		switch (n.tag) {
			case 26:
				Yc || Bc(n, t), il(e, t, n), n.memoizedState ? n.memoizedState.count-- : n.stateNode && (n = n.stateNode, n.parentNode.removeChild(n));
				break;
			case 27:
				Yc || Bc(n, t);
				var r = nl, i = rl;
				Zd(n.type) && (nl = n.stateNode, rl = !1), il(e, t, n), pf(n.stateNode), nl = r, rl = i;
				break;
			case 5: Yc || Bc(n, t);
			case 6:
				if (r = nl, i = rl, nl = null, il(e, t, n), nl = r, rl = i, nl !== null) if (rl) try {
					(nl.nodeType === 9 ? nl.body : nl.nodeName === "HTML" ? nl.ownerDocument.body : nl).removeChild(n.stateNode);
				} catch (e) {
					Uu(n, t, e);
				}
				else try {
					nl.removeChild(n.stateNode);
				} catch (e) {
					Uu(n, t, e);
				}
				break;
			case 18:
				nl !== null && (rl ? (e = nl, Qd(e.nodeType === 9 ? e.body : e.nodeName === "HTML" ? e.ownerDocument.body : e, n.stateNode), Np(e)) : Qd(nl, n.stateNode));
				break;
			case 4:
				r = nl, i = rl, nl = n.stateNode.containerInfo, rl = !0, il(e, t, n), nl = r, rl = i;
				break;
			case 0:
			case 11:
			case 14:
			case 15:
				Ic(2, n, t), Yc || Ic(4, n, t), il(e, t, n);
				break;
			case 1:
				Yc || (Bc(n, t), r = n.stateNode, typeof r.componentWillUnmount == "function" && Rc(n, t, r)), il(e, t, n);
				break;
			case 21:
				il(e, t, n);
				break;
			case 22:
				Yc = (r = Yc) || n.memoizedState !== null, il(e, t, n), Yc = r;
				break;
			default: il(e, t, n);
		}
	}
	function ol(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null))) {
			e = e.dehydrated;
			try {
				Np(e);
			} catch (e) {
				Uu(t, t.return, e);
			}
		}
	}
	function sl(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null && (e = e.dehydrated, e !== null)))) try {
			Np(e);
		} catch (e) {
			Uu(t, t.return, e);
		}
	}
	function cl(e) {
		switch (e.tag) {
			case 31:
			case 13:
			case 19:
				var t = e.stateNode;
				return t === null && (t = e.stateNode = new Zc()), t;
			case 22: return e = e.stateNode, t = e._retryCache, t === null && (t = e._retryCache = new Zc()), t;
			default: throw Error(s(435, e.tag));
		}
	}
	function ll(e, t) {
		var n = cl(e);
		t.forEach(function(t) {
			if (!n.has(t)) {
				n.add(t);
				var r = Ju.bind(null, e, t);
				t.then(r, r);
			}
		});
	}
	function ul(e, t) {
		var n = t.deletions;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = n[r], a = e, o = t, c = o;
			a: for (; c !== null;) {
				switch (c.tag) {
					case 27:
						if (Zd(c.type)) {
							nl = c.stateNode, rl = !1;
							break a;
						}
						break;
					case 5:
						nl = c.stateNode, rl = !1;
						break a;
					case 3:
					case 4:
						nl = c.stateNode.containerInfo, rl = !0;
						break a;
				}
				c = c.return;
			}
			if (nl === null) throw Error(s(160));
			al(a, o, i), nl = null, rl = !1, a = i.alternate, a !== null && (a.return = null), i.return = null;
		}
		if (t.subtreeFlags & 13886) for (t = t.child; t !== null;) fl(t, e), t = t.sibling;
	}
	var dl = null;
	function fl(e, t) {
		var n = e.alternate, r = e.flags;
		switch (e.tag) {
			case 0:
			case 11:
			case 14:
			case 15:
				ul(t, e), pl(e), r & 4 && (Ic(3, e, e.return), Fc(3, e), Ic(5, e, e.return));
				break;
			case 1:
				ul(t, e), pl(e), r & 512 && (Yc || n === null || Bc(n, n.return)), r & 64 && Jc && (e = e.updateQueue, e !== null && (r = e.callbacks, r !== null && (n = e.shared.hiddenCallbacks, e.shared.hiddenCallbacks = n === null ? r : n.concat(r))));
				break;
			case 26:
				var i = dl;
				if (ul(t, e), pl(e), r & 512 && (Yc || n === null || Bc(n, n.return)), r & 4) {
					var a = n === null ? null : n.memoizedState;
					if (r = e.memoizedState, n === null) if (r === null) if (e.stateNode === null) {
						a: {
							r = e.type, n = e.memoizedProps, i = i.ownerDocument || i;
							b: switch (r) {
								case "title":
									a = i.getElementsByTagName("title")[0], (!a || a[it] || a[Ze] || a.namespaceURI === "http://www.w3.org/2000/svg" || a.hasAttribute("itemprop")) && (a = i.createElement(r), i.head.insertBefore(a, i.querySelector("head > title"))), Pd(a, r, n), a[Ze] = e, ut(a), r = a;
									break a;
								case "link":
									var o = Vf("link", "href", i).get(r + (n.href || ""));
									if (o) {
										for (var c = 0; c < o.length; c++) if (a = o[c], a.getAttribute("href") === (n.href == null || n.href === "" ? null : n.href) && a.getAttribute("rel") === (n.rel == null ? null : n.rel) && a.getAttribute("title") === (n.title == null ? null : n.title) && a.getAttribute("crossorigin") === (n.crossOrigin == null ? null : n.crossOrigin)) {
											o.splice(c, 1);
											break b;
										}
									}
									a = i.createElement(r), Pd(a, r, n), i.head.appendChild(a);
									break;
								case "meta":
									if (o = Vf("meta", "content", i).get(r + (n.content || ""))) {
										for (c = 0; c < o.length; c++) if (a = o[c], a.getAttribute("content") === (n.content == null ? null : "" + n.content) && a.getAttribute("name") === (n.name == null ? null : n.name) && a.getAttribute("property") === (n.property == null ? null : n.property) && a.getAttribute("http-equiv") === (n.httpEquiv == null ? null : n.httpEquiv) && a.getAttribute("charset") === (n.charSet == null ? null : n.charSet)) {
											o.splice(c, 1);
											break b;
										}
									}
									a = i.createElement(r), Pd(a, r, n), i.head.appendChild(a);
									break;
								default: throw Error(s(468, r));
							}
							a[Ze] = e, ut(a), r = a;
						}
						e.stateNode = r;
					} else Hf(i, e.type, e.stateNode);
					else e.stateNode = If(i, r, e.memoizedProps);
					else a === r ? r === null && e.stateNode !== null && Hc(e, e.memoizedProps, n.memoizedProps) : (a === null ? n.stateNode !== null && (n = n.stateNode, n.parentNode.removeChild(n)) : a.count--, r === null ? Hf(i, e.type, e.stateNode) : If(i, r, e.memoizedProps));
				}
				break;
			case 27:
				ul(t, e), pl(e), r & 512 && (Yc || n === null || Bc(n, n.return)), n !== null && r & 4 && Hc(e, e.memoizedProps, n.memoizedProps);
				break;
			case 5:
				if (ul(t, e), pl(e), r & 512 && (Yc || n === null || Bc(n, n.return)), e.flags & 32) {
					i = e.stateNode;
					try {
						It(i, "");
					} catch (t) {
						Uu(e, e.return, t);
					}
				}
				r & 4 && e.stateNode != null && (i = e.memoizedProps, Hc(e, i, n === null ? i : n.memoizedProps)), r & 1024 && (Xc = !0);
				break;
			case 6:
				if (ul(t, e), pl(e), r & 4) {
					if (e.stateNode === null) throw Error(s(162));
					r = e.memoizedProps, n = e.stateNode;
					try {
						n.nodeValue = r;
					} catch (t) {
						Uu(e, e.return, t);
					}
				}
				break;
			case 3:
				if (Bf = null, i = dl, dl = gf(t.containerInfo), ul(t, e), dl = i, pl(e), r & 4 && n !== null && n.memoizedState.isDehydrated) try {
					Np(t.containerInfo);
				} catch (t) {
					Uu(e, e.return, t);
				}
				Xc && (Xc = !1, ml(e));
				break;
			case 4:
				r = dl, dl = gf(e.stateNode.containerInfo), ul(t, e), pl(e), dl = r;
				break;
			case 12:
				ul(t, e), pl(e);
				break;
			case 31:
				ul(t, e), pl(e), r & 4 && (r = e.updateQueue, r !== null && (e.updateQueue = null, ll(e, r)));
				break;
			case 13:
				ul(t, e), pl(e), e.child.flags & 8192 && e.memoizedState !== null != (n !== null && n.memoizedState !== null) && (Zl = ge()), r & 4 && (r = e.updateQueue, r !== null && (e.updateQueue = null, ll(e, r)));
				break;
			case 22:
				i = e.memoizedState !== null;
				var l = n !== null && n.memoizedState !== null, u = Jc, d = Yc;
				if (Jc = u || i, Yc = d || l, ul(t, e), Yc = d, Jc = u, pl(e), r & 8192) a: for (t = e.stateNode, t._visibility = i ? t._visibility & -2 : t._visibility | 1, i && (n === null || l || Jc || Yc || gl(e)), n = null, t = e;;) {
					if (t.tag === 5 || t.tag === 26) {
						if (n === null) {
							l = n = t;
							try {
								if (a = l.stateNode, i) o = a.style, typeof o.setProperty == "function" ? o.setProperty("display", "none", "important") : o.display = "none";
								else {
									c = l.stateNode;
									var f = l.memoizedProps.style, p = f != null && f.hasOwnProperty("display") ? f.display : null;
									c.style.display = p == null || typeof p == "boolean" ? "" : ("" + p).trim();
								}
							} catch (e) {
								Uu(l, l.return, e);
							}
						}
					} else if (t.tag === 6) {
						if (n === null) {
							l = t;
							try {
								l.stateNode.nodeValue = i ? "" : l.memoizedProps;
							} catch (e) {
								Uu(l, l.return, e);
							}
						}
					} else if (t.tag === 18) {
						if (n === null) {
							l = t;
							try {
								var m = l.stateNode;
								i ? $d(m, !0) : $d(l.stateNode, !1);
							} catch (e) {
								Uu(l, l.return, e);
							}
						}
					} else if ((t.tag !== 22 && t.tag !== 23 || t.memoizedState === null || t === e) && t.child !== null) {
						t.child.return = t, t = t.child;
						continue;
					}
					if (t === e) break a;
					for (; t.sibling === null;) {
						if (t.return === null || t.return === e) break a;
						n === t && (n = null), t = t.return;
					}
					n === t && (n = null), t.sibling.return = t.return, t = t.sibling;
				}
				r & 4 && (r = e.updateQueue, r !== null && (n = r.retryQueue, n !== null && (r.retryQueue = null, ll(e, n))));
				break;
			case 19:
				ul(t, e), pl(e), r & 4 && (r = e.updateQueue, r !== null && (e.updateQueue = null, ll(e, r)));
				break;
			case 30: break;
			case 21: break;
			default: ul(t, e), pl(e);
		}
	}
	function pl(e) {
		var t = e.flags;
		if (t & 2) {
			try {
				for (var n, r = e.return; r !== null;) {
					if (Uc(r)) {
						n = r;
						break;
					}
					r = r.return;
				}
				if (n == null) throw Error(s(160));
				switch (n.tag) {
					case 27:
						var i = n.stateNode;
						Kc(e, Wc(e), i);
						break;
					case 5:
						var a = n.stateNode;
						n.flags & 32 && (It(a, ""), n.flags &= -33), Kc(e, Wc(e), a);
						break;
					case 3:
					case 4:
						var o = n.stateNode.containerInfo;
						Gc(e, Wc(e), o);
						break;
					default: throw Error(s(161));
				}
			} catch (t) {
				Uu(e, e.return, t);
			}
			e.flags &= -3;
		}
		t & 4096 && (e.flags &= -4097);
	}
	function ml(e) {
		if (e.subtreeFlags & 1024) for (e = e.child; e !== null;) {
			var t = e;
			ml(t), t.tag === 5 && t.flags & 1024 && t.stateNode.reset(), e = e.sibling;
		}
	}
	function hl(e, t) {
		if (t.subtreeFlags & 8772) for (t = t.child; t !== null;) el(e, t.alternate, t), t = t.sibling;
	}
	function gl(e) {
		for (e = e.child; e !== null;) {
			var t = e;
			switch (t.tag) {
				case 0:
				case 11:
				case 14:
				case 15:
					Ic(4, t, t.return), gl(t);
					break;
				case 1:
					Bc(t, t.return);
					var n = t.stateNode;
					typeof n.componentWillUnmount == "function" && Rc(t, t.return, n), gl(t);
					break;
				case 27: pf(t.stateNode);
				case 26:
				case 5:
					Bc(t, t.return), gl(t);
					break;
				case 22:
					t.memoizedState === null && gl(t);
					break;
				case 30:
					gl(t);
					break;
				default: gl(t);
			}
			e = e.sibling;
		}
	}
	function _l(e, t, n) {
		for (n &&= !!(t.subtreeFlags & 8772), t = t.child; t !== null;) {
			var r = t.alternate, i = e, a = t, o = a.flags;
			switch (a.tag) {
				case 0:
				case 11:
				case 15:
					_l(i, a, n), Fc(4, a);
					break;
				case 1:
					if (_l(i, a, n), r = a, i = r.stateNode, typeof i.componentDidMount == "function") try {
						i.componentDidMount();
					} catch (e) {
						Uu(r, r.return, e);
					}
					if (r = a, i = r.updateQueue, i !== null) {
						var s = r.stateNode;
						try {
							var c = i.shared.hiddenCallbacks;
							if (c !== null) for (i.shared.hiddenCallbacks = null, i = 0; i < c.length; i++) Va(c[i], s);
						} catch (e) {
							Uu(r, r.return, e);
						}
					}
					n && o & 64 && Lc(a), zc(a, a.return);
					break;
				case 27: qc(a);
				case 26:
				case 5:
					_l(i, a, n), n && r === null && o & 4 && Vc(a), zc(a, a.return);
					break;
				case 12:
					_l(i, a, n);
					break;
				case 31:
					_l(i, a, n), n && o & 4 && ol(i, a);
					break;
				case 13:
					_l(i, a, n), n && o & 4 && sl(i, a);
					break;
				case 22:
					a.memoizedState === null && _l(i, a, n), zc(a, a.return);
					break;
				case 30: break;
				default: _l(i, a, n);
			}
			t = t.sibling;
		}
	}
	function vl(e, t) {
		var n = null;
		e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), e = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (e = t.memoizedState.cachePool.pool), e !== n && (e != null && e.refCount++, n != null && ea(n));
	}
	function yl(e, t) {
		e = null, t.alternate !== null && (e = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== e && (t.refCount++, e != null && ea(e));
	}
	function bl(e, t, n, r) {
		if (t.subtreeFlags & 10256) for (t = t.child; t !== null;) xl(e, t, n, r), t = t.sibling;
	}
	function xl(e, t, n, r) {
		var i = t.flags;
		switch (t.tag) {
			case 0:
			case 11:
			case 15:
				bl(e, t, n, r), i & 2048 && Fc(9, t);
				break;
			case 1:
				bl(e, t, n, r);
				break;
			case 3:
				bl(e, t, n, r), i & 2048 && (e = null, t.alternate !== null && (e = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== e && (t.refCount++, e != null && ea(e)));
				break;
			case 12:
				if (i & 2048) {
					bl(e, t, n, r), e = t.stateNode;
					try {
						var a = t.memoizedProps, o = a.id, s = a.onPostCommit;
						typeof s == "function" && s(o, t.alternate === null ? "mount" : "update", e.passiveEffectDuration, -0);
					} catch (e) {
						Uu(t, t.return, e);
					}
				} else bl(e, t, n, r);
				break;
			case 31:
				bl(e, t, n, r);
				break;
			case 13:
				bl(e, t, n, r);
				break;
			case 23: break;
			case 22:
				a = t.stateNode, o = t.alternate, t.memoizedState === null ? a._visibility & 2 ? bl(e, t, n, r) : (a._visibility |= 2, Sl(e, t, n, r, !!(t.subtreeFlags & 10256) || !1)) : a._visibility & 2 ? bl(e, t, n, r) : Cl(e, t), i & 2048 && vl(o, t);
				break;
			case 24:
				bl(e, t, n, r), i & 2048 && yl(t.alternate, t);
				break;
			default: bl(e, t, n, r);
		}
	}
	function Sl(e, t, n, r, i) {
		for (i &&= !!(t.subtreeFlags & 10256) || !1, t = t.child; t !== null;) {
			var a = e, o = t, s = n, c = r, l = o.flags;
			switch (o.tag) {
				case 0:
				case 11:
				case 15:
					Sl(a, o, s, c, i), Fc(8, o);
					break;
				case 23: break;
				case 22:
					var u = o.stateNode;
					o.memoizedState === null ? (u._visibility |= 2, Sl(a, o, s, c, i)) : u._visibility & 2 ? Sl(a, o, s, c, i) : Cl(a, o), i && l & 2048 && vl(o.alternate, o);
					break;
				case 24:
					Sl(a, o, s, c, i), i && l & 2048 && yl(o.alternate, o);
					break;
				default: Sl(a, o, s, c, i);
			}
			t = t.sibling;
		}
	}
	function Cl(e, t) {
		if (t.subtreeFlags & 10256) for (t = t.child; t !== null;) {
			var n = e, r = t, i = r.flags;
			switch (r.tag) {
				case 22:
					Cl(n, r), i & 2048 && vl(r.alternate, r);
					break;
				case 24:
					Cl(n, r), i & 2048 && yl(r.alternate, r);
					break;
				default: Cl(n, r);
			}
			t = t.sibling;
		}
	}
	var wl = 8192;
	function Tl(e, t, n) {
		if (e.subtreeFlags & wl) for (e = e.child; e !== null;) El(e, t, n), e = e.sibling;
	}
	function El(e, t, n) {
		switch (e.tag) {
			case 26:
				Tl(e, t, n), e.flags & wl && e.memoizedState !== null && Gf(n, dl, e.memoizedState, e.memoizedProps);
				break;
			case 5:
				Tl(e, t, n);
				break;
			case 3:
			case 4:
				var r = dl;
				dl = gf(e.stateNode.containerInfo), Tl(e, t, n), dl = r;
				break;
			case 22:
				e.memoizedState === null && (r = e.alternate, r !== null && r.memoizedState !== null ? (r = wl, wl = 16777216, Tl(e, t, n), wl = r) : Tl(e, t, n));
				break;
			default: Tl(e, t, n);
		}
	}
	function Dl(e) {
		var t = e.alternate;
		if (t !== null && (e = t.child, e !== null)) {
			t.child = null;
			do
				t = e.sibling, e.sibling = null, e = t;
			while (e !== null);
		}
	}
	function Ol(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				Qc = r, jl(r, e);
			}
			Dl(e);
		}
		if (e.subtreeFlags & 10256) for (e = e.child; e !== null;) kl(e), e = e.sibling;
	}
	function kl(e) {
		switch (e.tag) {
			case 0:
			case 11:
			case 15:
				Ol(e), e.flags & 2048 && Ic(9, e, e.return);
				break;
			case 3:
				Ol(e);
				break;
			case 12:
				Ol(e);
				break;
			case 22:
				var t = e.stateNode;
				e.memoizedState !== null && t._visibility & 2 && (e.return === null || e.return.tag !== 13) ? (t._visibility &= -3, Al(e)) : Ol(e);
				break;
			default: Ol(e);
		}
	}
	function Al(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				Qc = r, jl(r, e);
			}
			Dl(e);
		}
		for (e = e.child; e !== null;) {
			switch (t = e, t.tag) {
				case 0:
				case 11:
				case 15:
					Ic(8, t, t.return), Al(t);
					break;
				case 22:
					n = t.stateNode, n._visibility & 2 && (n._visibility &= -3, Al(t));
					break;
				default: Al(t);
			}
			e = e.sibling;
		}
	}
	function jl(e, t) {
		for (; Qc !== null;) {
			var n = Qc;
			switch (n.tag) {
				case 0:
				case 11:
				case 15:
					Ic(8, n, t);
					break;
				case 23:
				case 22:
					if (n.memoizedState !== null && n.memoizedState.cachePool !== null) {
						var r = n.memoizedState.cachePool.pool;
						r != null && r.refCount++;
					}
					break;
				case 24: ea(n.memoizedState.cache);
			}
			if (r = n.child, r !== null) r.return = n, Qc = r;
			else a: for (n = e; Qc !== null;) {
				r = Qc;
				var i = r.sibling, a = r.return;
				if (tl(r), r === n) {
					Qc = null;
					break a;
				}
				if (i !== null) {
					i.return = a, Qc = i;
					break a;
				}
				Qc = a;
			}
		}
	}
	var Ml = {
		getCacheForType: function(e) {
			var t = Ki(Qi), n = t.data.get(e);
			return n === void 0 && (n = e(), t.data.set(e, n)), n;
		},
		cacheSignal: function() {
			return Ki(Qi).controller.signal;
		}
	}, Nl = typeof WeakMap == "function" ? WeakMap : Map, Pl = 0, Fl = null, Z = null, Q = 0, Il = 0, Ll = null, Rl = !1, zl = !1, Bl = !1, Vl = 0, Hl = 0, Ul = 0, Wl = 0, Gl = 0, Kl = 0, ql = 0, Jl = null, Yl = null, Xl = !1, Zl = 0, Ql = 0, $l = Infinity, eu = null, tu = null, nu = 0, ru = null, iu = null, au = 0, ou = 0, su = null, cu = null, lu = 0, uu = null;
	function du() {
		return Pl & 2 && Q !== 0 ? Q & -Q : I.T === null ? Je() : ud();
	}
	function fu() {
		if (Kl === 0) if (!(Q & 536870912) || Ti) {
			var e = Ne;
			Ne <<= 1, !(Ne & 3932160) && (Ne = 262144), Kl = e;
		} else Kl = 536870912;
		return e = Ja.current, e !== null && (e.flags |= 32), Kl;
	}
	function pu(e, t, n) {
		(e === Fl && (Il === 2 || Il === 9) || e.cancelPendingCommit !== null) && (bu(e, 0), _u(e, Q, Kl, !1)), Ve(e, n), (!(Pl & 2) || e !== Fl) && (e === Fl && (!(Pl & 2) && (Wl |= n), Hl === 4 && _u(e, Q, Kl, !1)), nd(e));
	}
	function mu(e, t, n) {
		if (Pl & 6) throw Error(s(327));
		var r = !n && !(t & 127) && (t & e.expiredLanes) === 0 || Le(e, t), i = r ? Ou(e, t) : Eu(e, t, !0), a = r;
		do {
			if (i === 0) {
				zl && !r && _u(e, t, 0, !1);
				break;
			}
			if (n = e.current.alternate, a && !gu(n)) {
				i = Eu(e, t, !1), a = !1;
				continue;
			}
			if (i === 2) {
				if (a = t, e.errorRecoveryDisabledLanes & a) var o = 0;
				else o = e.pendingLanes & -536870913, o = o === 0 ? o & 536870912 ? 536870912 : 0 : o;
				if (o !== 0) {
					t = o;
					a: {
						var c = e;
						i = Jl;
						var l = c.current.memoizedState.isDehydrated;
						if (l && (bu(c, o).flags |= 256), o = Eu(c, o, !1), o !== 2) {
							if (Bl && !l) {
								c.errorRecoveryDisabledLanes |= a, Wl |= a, i = 4;
								break a;
							}
							a = Yl, Yl = i, a !== null && (Yl === null ? Yl = a : Yl.push.apply(Yl, a));
						}
						i = o;
					}
					if (a = !1, i !== 2) continue;
				}
			}
			if (i === 1) {
				bu(e, 0), _u(e, t, 0, !0);
				break;
			}
			a: {
				switch (r = e, a = i, a) {
					case 0:
					case 1: throw Error(s(345));
					case 4: if ((t & 4194048) !== t) break;
					case 6:
						_u(r, t, Kl, !Rl);
						break a;
					case 2:
						Yl = null;
						break;
					case 3:
					case 5: break;
					default: throw Error(s(329));
				}
				if ((t & 62914560) === t && (i = Zl + 300 - ge(), 10 < i)) {
					if (_u(r, t, Kl, !Rl), Ie(r, 0, !0) !== 0) break a;
					au = t, r.timeoutHandle = Kd(hu.bind(null, r, n, Yl, eu, Xl, t, Kl, Wl, ql, Rl, a, "Throttled", -0, 0), i);
					break a;
				}
				hu(r, n, Yl, eu, Xl, t, Kl, Wl, ql, Rl, a, null, -0, 0);
			}
			break;
		} while (1);
		nd(e);
	}
	function hu(e, t, n, r, i, a, o, s, c, l, u, d, f, p) {
		if (e.timeoutHandle = -1, d = t.subtreeFlags, d & 8192 || (d & 16785408) == 16785408) {
			d = {
				stylesheets: null,
				count: 0,
				imgCount: 0,
				imgBytes: 0,
				suspenseyImages: [],
				waitingForImages: !0,
				waitingForViewTransition: !1,
				unsuspend: Wt
			}, El(t, a, d);
			var m = (a & 62914560) === a ? Zl - ge() : (a & 4194048) === a ? Ql - ge() : 0;
			if (m = qf(d, m), m !== null) {
				au = a, e.cancelPendingCommit = m(Fu.bind(null, e, t, a, n, r, i, o, s, c, u, d, null, f, p)), _u(e, a, o, !l);
				return;
			}
		}
		Fu(e, t, a, n, r, i, o, s, c);
	}
	function gu(e) {
		for (var t = e;;) {
			var n = t.tag;
			if ((n === 0 || n === 11 || n === 15) && t.flags & 16384 && (n = t.updateQueue, n !== null && (n = n.stores, n !== null))) for (var r = 0; r < n.length; r++) {
				var i = n[r], a = i.getSnapshot;
				i = i.value;
				try {
					if (!fr(a(), i)) return !1;
				} catch {
					return !1;
				}
			}
			if (n = t.child, t.subtreeFlags & 16384 && n !== null) n.return = t, t = n;
			else {
				if (t === e) break;
				for (; t.sibling === null;) {
					if (t.return === null || t.return === e) return !0;
					t = t.return;
				}
				t.sibling.return = t.return, t = t.sibling;
			}
		}
		return !0;
	}
	function _u(e, t, n, r) {
		t &= ~Gl, t &= ~Wl, e.suspendedLanes |= t, e.pingedLanes &= ~t, r && (e.warmLanes |= t), r = e.expirationTimes;
		for (var i = t; 0 < i;) {
			var a = 31 - Oe(i), o = 1 << a;
			r[a] = -1, i &= ~o;
		}
		n !== 0 && Ue(e, n, t);
	}
	function vu() {
		return Pl & 6 ? !0 : (rd(0, !1), !1);
	}
	function yu() {
		if (Z !== null) {
			if (Il === 0) var e = Z.return;
			else e = Z, Ri = Li = null, xo(e), Ca = null, wa = 0, e = Z;
			for (; e !== null;) Pc(e.alternate, e), e = e.return;
			Z = null;
		}
	}
	function bu(e, t) {
		var n = e.timeoutHandle;
		n !== -1 && (e.timeoutHandle = -1, qd(n)), n = e.cancelPendingCommit, n !== null && (e.cancelPendingCommit = null, n()), au = 0, yu(), Fl = e, Z = n = ei(e.current, null), Q = t, Il = 0, Ll = null, Rl = !1, zl = Le(e, t), Bl = !1, ql = Kl = Gl = Wl = Ul = Hl = 0, Yl = Jl = null, Xl = !1, t & 8 && (t |= t & 32);
		var r = e.entangledLanes;
		if (r !== 0) for (e = e.entanglements, r &= t; 0 < r;) {
			var i = 31 - Oe(r), a = 1 << i;
			t |= e[i], r &= ~a;
		}
		return Vl = t, Wr(), n;
	}
	function xu(e, t) {
		Y = null, I.H = js, t === pa || t === ha ? (t = xa(), Il = 3) : t === ma ? (t = xa(), Il = 4) : Il = t === Ys ? 8 : typeof t == "object" && t && typeof t.then == "function" ? 6 : 1, Ll = t, Z === null && (Hl = 1, Us(e, ci(t, e.current)));
	}
	function Su() {
		var e = Ja.current;
		return e === null ? !0 : (Q & 4194048) === Q ? Ya === null : (Q & 62914560) === Q || Q & 536870912 ? e === Ya : !1;
	}
	function Cu() {
		var e = I.H;
		return I.H = js, e === null ? js : e;
	}
	function wu() {
		var e = I.A;
		return I.A = Ml, e;
	}
	function Tu() {
		Hl = 4, Rl || (Q & 4194048) !== Q && Ja.current !== null || (zl = !0), !(Ul & 134217727) && !(Wl & 134217727) || Fl === null || _u(Fl, Q, Kl, !1);
	}
	function Eu(e, t, n) {
		var r = Pl;
		Pl |= 2;
		var i = Cu(), a = wu();
		(Fl !== e || Q !== t) && (eu = null, bu(e, t)), t = !1;
		var o = Hl;
		a: do
			try {
				if (Il !== 0 && Z !== null) {
					var s = Z, c = Ll;
					switch (Il) {
						case 8:
							yu(), o = 6;
							break a;
						case 3:
						case 2:
						case 9:
						case 6:
							Ja.current === null && (t = !0);
							var l = Il;
							if (Il = 0, Ll = null, Mu(e, s, c, l), n && zl) {
								o = 0;
								break a;
							}
							break;
						default: l = Il, Il = 0, Ll = null, Mu(e, s, c, l);
					}
				}
				Du(), o = Hl;
				break;
			} catch (t) {
				xu(e, t);
			}
		while (1);
		return t && e.shellSuspendCounter++, Ri = Li = null, Pl = r, I.H = i, I.A = a, Z === null && (Fl = null, Q = 0, Wr()), o;
	}
	function Du() {
		for (; Z !== null;) Au(Z);
	}
	function Ou(e, t) {
		var n = Pl;
		Pl |= 2;
		var r = Cu(), i = wu();
		Fl !== e || Q !== t ? (eu = null, $l = ge() + 500, bu(e, t)) : zl = Le(e, t);
		a: do
			try {
				if (Il !== 0 && Z !== null) {
					t = Z;
					var a = Ll;
					b: switch (Il) {
						case 1:
							Il = 0, Ll = null, Mu(e, t, a, 1);
							break;
						case 2:
						case 9:
							if (_a(a)) {
								Il = 0, Ll = null, ju(t);
								break;
							}
							t = function() {
								Il !== 2 && Il !== 9 || Fl !== e || (Il = 7), nd(e);
							}, a.then(t, t);
							break a;
						case 3:
							Il = 7;
							break a;
						case 4:
							Il = 5;
							break a;
						case 7:
							_a(a) ? (Il = 0, Ll = null, ju(t)) : (Il = 0, Ll = null, Mu(e, t, a, 7));
							break;
						case 5:
							var o = null;
							switch (Z.tag) {
								case 26: o = Z.memoizedState;
								case 5:
								case 27:
									var c = Z;
									if (o ? Wf(o) : c.stateNode.complete) {
										Il = 0, Ll = null;
										var l = c.sibling;
										if (l !== null) Z = l;
										else {
											var u = c.return;
											u === null ? Z = null : (Z = u, Nu(u));
										}
										break b;
									}
							}
							Il = 0, Ll = null, Mu(e, t, a, 5);
							break;
						case 6:
							Il = 0, Ll = null, Mu(e, t, a, 6);
							break;
						case 8:
							yu(), Hl = 6;
							break a;
						default: throw Error(s(462));
					}
				}
				ku();
				break;
			} catch (t) {
				xu(e, t);
			}
		while (1);
		return Ri = Li = null, I.H = r, I.A = i, Pl = n, Z === null ? (Fl = null, Q = 0, Wr(), Hl) : 0;
	}
	function ku() {
		for (; Z !== null && !me();) Au(Z);
	}
	function Au(e) {
		var t = Tc(e.alternate, e, Vl);
		e.memoizedProps = e.pendingProps, t === null ? Nu(e) : Z = t;
	}
	function ju(e) {
		var t = e, n = t.alternate;
		switch (t.tag) {
			case 15:
			case 0:
				t = lc(n, t, t.pendingProps, t.type, void 0, Q);
				break;
			case 11:
				t = lc(n, t, t.pendingProps, t.type.render, t.ref, Q);
				break;
			case 5: xo(t);
			default: Pc(n, t), t = Z = ti(t, Vl), t = Tc(n, t, Vl);
		}
		e.memoizedProps = e.pendingProps, t === null ? Nu(e) : Z = t;
	}
	function Mu(e, t, n, r) {
		Ri = Li = null, xo(t), Ca = null, wa = 0;
		var i = t.return;
		try {
			if (Js(e, i, t, n, Q)) {
				Hl = 1, Us(e, ci(n, e.current)), Z = null;
				return;
			}
		} catch (t) {
			if (i !== null) throw Z = i, t;
			Hl = 1, Us(e, ci(n, e.current)), Z = null;
			return;
		}
		t.flags & 32768 ? (Ti || r === 1 ? e = !0 : zl || Q & 536870912 ? e = !1 : (Rl = e = !0, (r === 2 || r === 9 || r === 3 || r === 6) && (r = Ja.current, r !== null && r.tag === 13 && (r.flags |= 16384))), Pu(t, e)) : Nu(t);
	}
	function Nu(e) {
		var t = e;
		do {
			if (t.flags & 32768) {
				Pu(t, Rl);
				return;
			}
			e = t.return;
			var n = Mc(t.alternate, t, Vl);
			if (n !== null) {
				Z = n;
				return;
			}
			if (t = t.sibling, t !== null) {
				Z = t;
				return;
			}
			Z = t = e;
		} while (t !== null);
		Hl === 0 && (Hl = 5);
	}
	function Pu(e, t) {
		do {
			var n = Nc(e.alternate, e);
			if (n !== null) {
				n.flags &= 32767, Z = n;
				return;
			}
			if (n = e.return, n !== null && (n.flags |= 32768, n.subtreeFlags = 0, n.deletions = null), !t && (e = e.sibling, e !== null)) {
				Z = e;
				return;
			}
			Z = e = n;
		} while (e !== null);
		Hl = 6, Z = null;
	}
	function Fu(e, t, n, r, i, a, o, c, l) {
		e.cancelPendingCommit = null;
		do
			Bu();
		while (nu !== 0);
		if (Pl & 6) throw Error(s(327));
		if (t !== null) {
			if (t === e.current) throw Error(s(177));
			if (a = t.lanes | t.childLanes, a |= Ur, He(e, n, a, o, c, l), e === Fl && (Z = Fl = null, Q = 0), iu = t, ru = e, au = n, ou = a, su = i, cu = r, t.subtreeFlags & 10256 || t.flags & 10256 ? (e.callbackNode = null, e.callbackPriority = 0, Yu(be, function() {
				return Vu(), null;
			})) : (e.callbackNode = null, e.callbackPriority = 0), r = !!(t.flags & 13878), t.subtreeFlags & 13878 || r) {
				r = I.T, I.T = null, i = L.p, L.p = 2, o = Pl, Pl |= 4;
				try {
					$c(e, t, n);
				} finally {
					Pl = o, L.p = i, I.T = r;
				}
			}
			nu = 1, Iu(), Lu(), Ru();
		}
	}
	function Iu() {
		if (nu === 1) {
			nu = 0;
			var e = ru, t = iu, n = !!(t.flags & 13878);
			if (t.subtreeFlags & 13878 || n) {
				n = I.T, I.T = null;
				var r = L.p;
				L.p = 2;
				var i = Pl;
				Pl |= 4;
				try {
					fl(t, e);
					var a = zd, o = _r(e.containerInfo), s = a.focusedElem, c = a.selectionRange;
					if (o !== s && s && s.ownerDocument && gr(s.ownerDocument.documentElement, s)) {
						if (c !== null && vr(s)) {
							var l = c.start, u = c.end;
							if (u === void 0 && (u = l), "selectionStart" in s) s.selectionStart = l, s.selectionEnd = Math.min(u, s.value.length);
							else {
								var d = s.ownerDocument || document, f = d && d.defaultView || window;
								if (f.getSelection) {
									var p = f.getSelection(), m = s.textContent.length, h = Math.min(c.start, m), g = c.end === void 0 ? h : Math.min(c.end, m);
									!p.extend && h > g && (o = g, g = h, h = o);
									var _ = hr(s, h), v = hr(s, g);
									if (_ && v && (p.rangeCount !== 1 || p.anchorNode !== _.node || p.anchorOffset !== _.offset || p.focusNode !== v.node || p.focusOffset !== v.offset)) {
										var y = d.createRange();
										y.setStart(_.node, _.offset), p.removeAllRanges(), h > g ? (p.addRange(y), p.extend(v.node, v.offset)) : (y.setEnd(v.node, v.offset), p.addRange(y));
									}
								}
							}
						}
						for (d = [], p = s; p = p.parentNode;) p.nodeType === 1 && d.push({
							element: p,
							left: p.scrollLeft,
							top: p.scrollTop
						});
						for (typeof s.focus == "function" && s.focus(), s = 0; s < d.length; s++) {
							var b = d[s];
							b.element.scrollLeft = b.left, b.element.scrollTop = b.top;
						}
					}
					sp = !!Rd, zd = Rd = null;
				} finally {
					Pl = i, L.p = r, I.T = n;
				}
			}
			e.current = t, nu = 2;
		}
	}
	function Lu() {
		if (nu === 2) {
			nu = 0;
			var e = ru, t = iu, n = !!(t.flags & 8772);
			if (t.subtreeFlags & 8772 || n) {
				n = I.T, I.T = null;
				var r = L.p;
				L.p = 2;
				var i = Pl;
				Pl |= 4;
				try {
					el(e, t.alternate, t);
				} finally {
					Pl = i, L.p = r, I.T = n;
				}
			}
			nu = 3;
		}
	}
	function Ru() {
		if (nu === 4 || nu === 3) {
			nu = 0, he();
			var e = ru, t = iu, n = au, r = cu;
			t.subtreeFlags & 10256 || t.flags & 10256 ? nu = 5 : (nu = 0, iu = ru = null, zu(e, e.pendingLanes));
			var i = e.pendingLanes;
			if (i === 0 && (tu = null), qe(n), t = t.stateNode, Ee && typeof Ee.onCommitFiberRoot == "function") try {
				Ee.onCommitFiberRoot(Te, t, void 0, (t.current.flags & 128) == 128);
			} catch {}
			if (r !== null) {
				t = I.T, i = L.p, L.p = 2, I.T = null;
				try {
					for (var a = e.onRecoverableError, o = 0; o < r.length; o++) {
						var s = r[o];
						a(s.value, { componentStack: s.stack });
					}
				} finally {
					I.T = t, L.p = i;
				}
			}
			au & 3 && Bu(), nd(e), i = e.pendingLanes, n & 261930 && i & 42 ? e === uu ? lu++ : (lu = 0, uu = e) : lu = 0, rd(0, !1);
		}
	}
	function zu(e, t) {
		(e.pooledCacheLanes &= t) === 0 && (t = e.pooledCache, t != null && (e.pooledCache = null, ea(t)));
	}
	function Bu() {
		return Iu(), Lu(), Ru(), Vu();
	}
	function Vu() {
		if (nu !== 5) return !1;
		var e = ru, t = ou;
		ou = 0;
		var n = qe(au), r = I.T, i = L.p;
		try {
			L.p = 32 > n ? 32 : n, I.T = null, n = su, su = null;
			var a = ru, o = au;
			if (nu = 0, iu = ru = null, au = 0, Pl & 6) throw Error(s(331));
			var c = Pl;
			if (Pl |= 4, kl(a.current), xl(a, a.current, o, n), Pl = c, rd(0, !1), Ee && typeof Ee.onPostCommitFiberRoot == "function") try {
				Ee.onPostCommitFiberRoot(Te, a);
			} catch {}
			return !0;
		} finally {
			L.p = i, I.T = r, zu(e, t);
		}
	}
	function Hu(e, t, n) {
		t = ci(n, t), t = Gs(e.stateNode, t, 2), e = Fa(e, t, 2), e !== null && (Ve(e, 2), nd(e));
	}
	function Uu(e, t, n) {
		if (e.tag === 3) Hu(e, e, n);
		else for (; t !== null;) {
			if (t.tag === 3) {
				Hu(t, e, n);
				break;
			}
			if (t.tag === 1) {
				var r = t.stateNode;
				if (typeof t.type.getDerivedStateFromError == "function" || typeof r.componentDidCatch == "function" && (tu === null || !tu.has(r))) {
					e = ci(n, e), n = Ks(2), r = Fa(t, n, 2), r !== null && (qs(n, r, t, e), Ve(r, 2), nd(r));
					break;
				}
			}
			t = t.return;
		}
	}
	function Wu(e, t, n) {
		var r = e.pingCache;
		if (r === null) {
			r = e.pingCache = new Nl();
			var i = /* @__PURE__ */ new Set();
			r.set(t, i);
		} else i = r.get(t), i === void 0 && (i = /* @__PURE__ */ new Set(), r.set(t, i));
		i.has(n) || (Bl = !0, i.add(n), e = Gu.bind(null, e, t, n), t.then(e, e));
	}
	function Gu(e, t, n) {
		var r = e.pingCache;
		r !== null && r.delete(t), e.pingedLanes |= e.suspendedLanes & n, e.warmLanes &= ~n, Fl === e && (Q & n) === n && (Hl === 4 || Hl === 3 && (Q & 62914560) === Q && 300 > ge() - Zl ? !(Pl & 2) && bu(e, 0) : Gl |= n, ql === Q && (ql = 0)), nd(e);
	}
	function Ku(e, t) {
		t === 0 && (t = ze()), e = qr(e, t), e !== null && (Ve(e, t), nd(e));
	}
	function qu(e) {
		var t = e.memoizedState, n = 0;
		t !== null && (n = t.retryLane), Ku(e, n);
	}
	function Ju(e, t) {
		var n = 0;
		switch (e.tag) {
			case 31:
			case 13:
				var r = e.stateNode, i = e.memoizedState;
				i !== null && (n = i.retryLane);
				break;
			case 19:
				r = e.stateNode;
				break;
			case 22:
				r = e.stateNode._retryCache;
				break;
			default: throw Error(s(314));
		}
		r !== null && r.delete(t), Ku(e, n);
	}
	function Yu(e, t) {
		return fe(e, t);
	}
	var Xu = null, Zu = null, Qu = !1, $u = !1, ed = !1, td = 0;
	function nd(e) {
		e !== Zu && e.next === null && (Zu === null ? Xu = Zu = e : Zu = Zu.next = e), $u = !0, Qu || (Qu = !0, ld());
	}
	function rd(e, t) {
		if (!ed && $u) {
			ed = !0;
			do
				for (var n = !1, r = Xu; r !== null;) {
					if (!t) if (e !== 0) {
						var i = r.pendingLanes;
						if (i === 0) var a = 0;
						else {
							var o = r.suspendedLanes, s = r.pingedLanes;
							a = (1 << 31 - Oe(42 | e) + 1) - 1, a &= i & ~(o & ~s), a = a & 201326741 ? a & 201326741 | 1 : a ? a | 2 : 0;
						}
						a !== 0 && (n = !0, cd(r, a));
					} else a = Q, a = Ie(r, r === Fl ? a : 0, r.cancelPendingCommit !== null || r.timeoutHandle !== -1), !(a & 3) || Le(r, a) || (n = !0, cd(r, a));
					r = r.next;
				}
			while (n);
			ed = !1;
		}
	}
	function id() {
		ad();
	}
	function ad() {
		$u = Qu = !1;
		var e = 0;
		td !== 0 && Gd() && (e = td);
		for (var t = ge(), n = null, r = Xu; r !== null;) {
			var i = r.next, a = od(r, t);
			a === 0 ? (r.next = null, n === null ? Xu = i : n.next = i, i === null && (Zu = n)) : (n = r, (e !== 0 || a & 3) && ($u = !0)), r = i;
		}
		nu !== 0 && nu !== 5 || rd(e, !1), td !== 0 && (td = 0);
	}
	function od(e, t) {
		for (var n = e.suspendedLanes, r = e.pingedLanes, i = e.expirationTimes, a = e.pendingLanes & -62914561; 0 < a;) {
			var o = 31 - Oe(a), s = 1 << o, c = i[o];
			c === -1 ? ((s & n) === 0 || (s & r) !== 0) && (i[o] = Re(s, t)) : c <= t && (e.expiredLanes |= s), a &= ~s;
		}
		if (t = Fl, n = Q, n = Ie(e, e === t ? n : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r = e.callbackNode, n === 0 || e === t && (Il === 2 || Il === 9) || e.cancelPendingCommit !== null) return r !== null && r !== null && pe(r), e.callbackNode = null, e.callbackPriority = 0;
		if (!(n & 3) || Le(e, n)) {
			if (t = n & -n, t === e.callbackPriority) return t;
			switch (r !== null && pe(r), qe(n)) {
				case 2:
				case 8:
					n = ye;
					break;
				case 32:
					n = be;
					break;
				case 268435456:
					n = Se;
					break;
				default: n = be;
			}
			return r = sd.bind(null, e), n = fe(n, r), e.callbackPriority = t, e.callbackNode = n, t;
		}
		return r !== null && r !== null && pe(r), e.callbackPriority = 2, e.callbackNode = null, 2;
	}
	function sd(e, t) {
		if (nu !== 0 && nu !== 5) return e.callbackNode = null, e.callbackPriority = 0, null;
		var n = e.callbackNode;
		if (Bu() && e.callbackNode !== n) return null;
		var r = Q;
		return r = Ie(e, e === Fl ? r : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r === 0 ? null : (mu(e, r, t), od(e, ge()), e.callbackNode != null && e.callbackNode === n ? sd.bind(null, e) : null);
	}
	function cd(e, t) {
		if (Bu()) return null;
		mu(e, t, !0);
	}
	function ld() {
		Yd(function() {
			Pl & 6 ? fe(ve, id) : ad();
		});
	}
	function ud() {
		if (td === 0) {
			var e = ra;
			e === 0 && (e = Me, Me <<= 1, !(Me & 261888) && (Me = 256)), td = e;
		}
		return td;
	}
	function dd(e) {
		return e == null || typeof e == "symbol" || typeof e == "boolean" ? null : typeof e == "function" ? e : Ut("" + e);
	}
	function fd(e, t) {
		var n = t.ownerDocument.createElement("input");
		return n.name = t.name, n.value = t.value, e.id && n.setAttribute("form", e.id), t.parentNode.insertBefore(n, t), e = new FormData(e), n.parentNode.removeChild(n), e;
	}
	function pd(e, t, n, r, i) {
		if (t === "submit" && n && n.stateNode === i) {
			var a = dd((i[Qe] || null).action), o = r.submitter;
			o && (t = (t = o[Qe] || null) ? dd(t.formAction) : o.getAttribute("formAction"), t !== null && (a = t, o = null));
			var s = new fn("action", "action", null, r, i);
			e.push({
				event: s,
				listeners: [{
					instance: null,
					listener: function() {
						if (r.defaultPrevented) {
							if (td !== 0) {
								var e = o ? fd(i, o) : new FormData(i);
								_s(n, {
									pending: !0,
									data: e,
									method: i.method,
									action: a
								}, null, e);
							}
						} else typeof a == "function" && (s.preventDefault(), e = o ? fd(i, o) : new FormData(i), _s(n, {
							pending: !0,
							data: e,
							method: i.method,
							action: a
						}, a, e));
					},
					currentTarget: i
				}]
			});
		}
	}
	for (var md = 0; md < Rr.length; md++) {
		var hd = Rr[md];
		zr(hd.toLowerCase(), "on" + (hd[0].toUpperCase() + hd.slice(1)));
	}
	zr(Ar, "onAnimationEnd"), zr(jr, "onAnimationIteration"), zr(Mr, "onAnimationStart"), zr("dblclick", "onDoubleClick"), zr("focusin", "onFocus"), zr("focusout", "onBlur"), zr(Nr, "onTransitionRun"), zr(Pr, "onTransitionStart"), zr(Fr, "onTransitionCancel"), zr(Ir, "onTransitionEnd"), mt("onMouseEnter", ["mouseout", "mouseover"]), mt("onMouseLeave", ["mouseout", "mouseover"]), mt("onPointerEnter", ["pointerout", "pointerover"]), mt("onPointerLeave", ["pointerout", "pointerover"]), pt("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" ")), pt("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" ")), pt("onBeforeInput", [
		"compositionend",
		"keypress",
		"textInput",
		"paste"
	]), pt("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" ")), pt("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" ")), pt("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
	var gd = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), _d = new Set("beforetoggle cancel close invalid load scroll scrollend toggle".split(" ").concat(gd));
	function vd(e, t) {
		t = !!(t & 4);
		for (var n = 0; n < e.length; n++) {
			var r = e[n], i = r.event;
			r = r.listeners;
			a: {
				var a = void 0;
				if (t) for (var o = r.length - 1; 0 <= o; o--) {
					var s = r[o], c = s.instance, l = s.currentTarget;
					if (s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						Br(e);
					}
					i.currentTarget = null, a = c;
				}
				else for (o = 0; o < r.length; o++) {
					if (s = r[o], c = s.instance, l = s.currentTarget, s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						Br(e);
					}
					i.currentTarget = null, a = c;
				}
			}
		}
	}
	function $(e, t) {
		var n = t[et];
		n === void 0 && (n = t[et] = /* @__PURE__ */ new Set());
		var r = e + "__bubble";
		n.has(r) || (Sd(t, e, 2, !1), n.add(r));
	}
	function yd(e, t, n) {
		var r = 0;
		t && (r |= 4), Sd(n, e, r, t);
	}
	var bd = "_reactListening" + Math.random().toString(36).slice(2);
	function xd(e) {
		if (!e[bd]) {
			e[bd] = !0, dt.forEach(function(t) {
				t !== "selectionchange" && (_d.has(t) || yd(t, !1, e), yd(t, !0, e));
			});
			var t = e.nodeType === 9 ? e : e.ownerDocument;
			t === null || t[bd] || (t[bd] = !0, yd("selectionchange", !1, t));
		}
	}
	function Sd(e, t, n, r) {
		switch (mp(t)) {
			case 2:
				var i = cp;
				break;
			case 8:
				i = lp;
				break;
			default: i = up;
		}
		n = i.bind(null, t, n, e), i = void 0, !en || t !== "touchstart" && t !== "touchmove" && t !== "wheel" || (i = !0), r ? i === void 0 ? e.addEventListener(t, n, !0) : e.addEventListener(t, n, {
			capture: !0,
			passive: i
		}) : i === void 0 ? e.addEventListener(t, n, !1) : e.addEventListener(t, n, { passive: i });
	}
	function Cd(e, t, n, r, i) {
		var a = r;
		if (!(t & 1) && !(t & 2) && r !== null) a: for (;;) {
			if (r === null) return;
			var o = r.tag;
			if (o === 3 || o === 4) {
				var s = r.stateNode.containerInfo;
				if (s === i) break;
				if (o === 4) for (o = r.return; o !== null;) {
					var c = o.tag;
					if ((c === 3 || c === 4) && o.stateNode.containerInfo === i) return;
					o = o.return;
				}
				for (; s !== null;) {
					if (o = ot(s), o === null) return;
					if (c = o.tag, c === 5 || c === 6 || c === 26 || c === 27) {
						r = a = o;
						continue a;
					}
					s = s.parentNode;
				}
			}
			r = r.return;
		}
		Zt(function() {
			var r = a, i = Kt(n), o = [];
			a: {
				var s = Lr.get(e);
				if (s !== void 0) {
					var c = fn, u = e;
					switch (e) {
						case "keypress": if (sn(n) === 0) break a;
						case "keydown":
						case "keyup":
							c = An;
							break;
						case "focusin":
							u = "focus", c = xn;
							break;
						case "focusout":
							u = "blur", c = xn;
							break;
						case "beforeblur":
						case "afterblur":
							c = xn;
							break;
						case "click": if (n.button === 2) break a;
						case "auxclick":
						case "dblclick":
						case "mousedown":
						case "mousemove":
						case "mouseup":
						case "mouseout":
						case "mouseover":
						case "contextmenu":
							c = yn;
							break;
						case "drag":
						case "dragend":
						case "dragenter":
						case "dragexit":
						case "dragleave":
						case "dragover":
						case "dragstart":
						case "drop":
							c = bn;
							break;
						case "touchcancel":
						case "touchend":
						case "touchmove":
						case "touchstart":
							c = Mn;
							break;
						case Ar:
						case jr:
						case Mr:
							c = Sn;
							break;
						case Ir:
							c = Nn;
							break;
						case "scroll":
						case "scrollend":
							c = mn;
							break;
						case "wheel":
							c = Pn;
							break;
						case "copy":
						case "cut":
						case "paste":
							c = Cn;
							break;
						case "gotpointercapture":
						case "lostpointercapture":
						case "pointercancel":
						case "pointerdown":
						case "pointermove":
						case "pointerout":
						case "pointerover":
						case "pointerup":
							c = jn;
							break;
						case "toggle":
						case "beforetoggle": c = Fn;
					}
					var d = !!(t & 4), f = !d && (e === "scroll" || e === "scrollend"), p = d ? s === null ? null : s + "Capture" : s;
					d = [];
					for (var m = r, h; m !== null;) {
						var g = m;
						if (h = g.stateNode, g = g.tag, g !== 5 && g !== 26 && g !== 27 || h === null || p === null || (g = Qt(m, p), g != null && d.push(wd(m, g, h))), f) break;
						m = m.return;
					}
					0 < d.length && (s = new c(s, u, null, n, i), o.push({
						event: s,
						listeners: d
					}));
				}
			}
			if (!(t & 7)) {
				a: {
					if (s = e === "mouseover" || e === "pointerover", c = e === "mouseout" || e === "pointerout", s && n !== Gt && (u = n.relatedTarget || n.fromElement) && (ot(u) || u[$e])) break a;
					if ((c || s) && (s = i.window === i ? i : (s = i.ownerDocument) ? s.defaultView || s.parentWindow : window, c ? (u = n.relatedTarget || n.toElement, c = r, u = u ? ot(u) : null, u !== null && (f = l(u), d = u.tag, u !== f || d !== 5 && d !== 27 && d !== 6) && (u = null)) : (c = null, u = r), c !== u)) {
						if (d = yn, g = "onMouseLeave", p = "onMouseEnter", m = "mouse", (e === "pointerout" || e === "pointerover") && (d = jn, g = "onPointerLeave", p = "onPointerEnter", m = "pointer"), f = c == null ? s : ct(c), h = u == null ? s : ct(u), s = new d(g, m + "leave", c, n, i), s.target = f, s.relatedTarget = h, g = null, ot(i) === r && (d = new d(p, m + "enter", u, n, i), d.target = h, d.relatedTarget = f, g = d), f = g, c && u) b: {
							for (d = Ed, p = c, m = u, h = 0, g = p; g; g = d(g)) h++;
							g = 0;
							for (var _ = m; _; _ = d(_)) g++;
							for (; 0 < h - g;) p = d(p), h--;
							for (; 0 < g - h;) m = d(m), g--;
							for (; h--;) {
								if (p === m || m !== null && p === m.alternate) {
									d = p;
									break b;
								}
								p = d(p), m = d(m);
							}
							d = null;
						}
						else d = null;
						c !== null && Dd(o, s, c, d, !1), u !== null && f !== null && Dd(o, f, u, d, !0);
					}
				}
				a: {
					if (s = r ? ct(r) : window, c = s.nodeName && s.nodeName.toLowerCase(), c === "select" || c === "input" && s.type === "file") var v = tr;
					else if (Yn(s)) if (J) v = ur;
					else {
						v = cr;
						var y = sr;
					}
					else c = s.nodeName, !c || c.toLowerCase() !== "input" || s.type !== "checkbox" && s.type !== "radio" ? r && Bt(r.elementType) && (v = tr) : v = lr;
					if (v &&= v(e, r)) {
						Xn(o, v, n, i);
						break a;
					}
					y && y(e, s, r), e === "focusout" && r && s.type === "number" && r.memoizedProps.value != null && Mt(s, "number", s.value);
				}
				switch (y = r ? ct(r) : window, e) {
					case "focusin":
						(Yn(y) || y.contentEditable === "true") && (br = y, xr = r, Sr = null);
						break;
					case "focusout":
						Sr = xr = br = null;
						break;
					case "mousedown":
						Cr = !0;
						break;
					case "contextmenu":
					case "mouseup":
					case "dragend":
						Cr = !1, wr(o, n, i);
						break;
					case "selectionchange": if (yr) break;
					case "keydown":
					case "keyup": wr(o, n, i);
				}
				var b;
				if (Ln) b: {
					switch (e) {
						case "compositionstart":
							var x = "onCompositionStart";
							break b;
						case "compositionend":
							x = "onCompositionEnd";
							break b;
						case "compositionupdate":
							x = "onCompositionUpdate";
							break b;
					}
					x = void 0;
				}
				else Gn ? Un(e, n) && (x = "onCompositionEnd") : e === "keydown" && n.keyCode === 229 && (x = "onCompositionStart");
				x && (Bn && n.locale !== "ko" && (Gn || x !== "onCompositionStart" ? x === "onCompositionEnd" && Gn && (b = on()) : (nn = i, rn = "value" in nn ? nn.value : nn.textContent, Gn = !0)), y = Td(r, x), 0 < y.length && (x = new wn(x, e, null, n, i), o.push({
					event: x,
					listeners: y
				}), b ? x.data = b : (b = Wn(n), b !== null && (x.data = b)))), (b = zn ? Kn(e, n) : qn(e, n)) && (x = Td(r, "onBeforeInput"), 0 < x.length && (y = new wn("onBeforeInput", "beforeinput", null, n, i), o.push({
					event: y,
					listeners: x
				}), y.data = b)), pd(o, e, r, n, i);
			}
			vd(o, t);
		});
	}
	function wd(e, t, n) {
		return {
			instance: e,
			listener: t,
			currentTarget: n
		};
	}
	function Td(e, t) {
		for (var n = t + "Capture", r = []; e !== null;) {
			var i = e, a = i.stateNode;
			if (i = i.tag, i !== 5 && i !== 26 && i !== 27 || a === null || (i = Qt(e, n), i != null && r.unshift(wd(e, i, a)), i = Qt(e, t), i != null && r.push(wd(e, i, a))), e.tag === 3) return r;
			e = e.return;
		}
		return [];
	}
	function Ed(e) {
		if (e === null) return null;
		do
			e = e.return;
		while (e && e.tag !== 5 && e.tag !== 27);
		return e || null;
	}
	function Dd(e, t, n, r, i) {
		for (var a = t._reactName, o = []; n !== null && n !== r;) {
			var s = n, c = s.alternate, l = s.stateNode;
			if (s = s.tag, c !== null && c === r) break;
			s !== 5 && s !== 26 && s !== 27 || l === null || (c = l, i ? (l = Qt(n, a), l != null && o.unshift(wd(n, l, c))) : i || (l = Qt(n, a), l != null && o.push(wd(n, l, c)))), n = n.return;
		}
		o.length !== 0 && e.push({
			event: t,
			listeners: o
		});
	}
	var Od = /\r\n?/g, kd = /\u0000|\uFFFD/g;
	function Ad(e) {
		return (typeof e == "string" ? e : "" + e).replace(Od, "\n").replace(kd, "");
	}
	function jd(e, t) {
		return t = Ad(t), Ad(e) === t;
	}
	function Md(e, t, n, r, i, a) {
		switch (n) {
			case "children":
				typeof r == "string" ? t === "body" || t === "textarea" && r === "" || It(e, r) : (typeof r == "number" || typeof r == "bigint") && t !== "body" && It(e, "" + r);
				break;
			case "className":
				bt(e, "class", r);
				break;
			case "tabIndex":
				bt(e, "tabindex", r);
				break;
			case "dir":
			case "role":
			case "viewBox":
			case "width":
			case "height":
				bt(e, n, r);
				break;
			case "style":
				zt(e, r, a);
				break;
			case "data": if (t !== "object") {
				bt(e, "data", r);
				break;
			}
			case "src":
			case "href":
				if (r === "" && (t !== "a" || n !== "href")) {
					e.removeAttribute(n);
					break;
				}
				if (r == null || typeof r == "function" || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = Ut("" + r), e.setAttribute(n, r);
				break;
			case "action":
			case "formAction":
				if (typeof r == "function") {
					e.setAttribute(n, "javascript:throw new Error('A React form was unexpectedly submitted. If you called form.submit() manually, consider using form.requestSubmit() instead. If you\\'re trying to use event.stopPropagation() in a submit event handler, consider also calling event.preventDefault().')");
					break;
				}
				if (typeof a == "function" && (n === "formAction" ? (t !== "input" && Md(e, t, "name", i.name, i, null), Md(e, t, "formEncType", i.formEncType, i, null), Md(e, t, "formMethod", i.formMethod, i, null), Md(e, t, "formTarget", i.formTarget, i, null)) : (Md(e, t, "encType", i.encType, i, null), Md(e, t, "method", i.method, i, null), Md(e, t, "target", i.target, i, null))), r == null || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = Ut("" + r), e.setAttribute(n, r);
				break;
			case "onClick":
				r != null && (e.onclick = Wt);
				break;
			case "onScroll":
				r != null && $("scroll", e);
				break;
			case "onScrollEnd":
				r != null && $("scrollend", e);
				break;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						e.innerHTML = n;
					}
				}
				break;
			case "multiple":
				e.multiple = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "muted":
				e.muted = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "defaultValue":
			case "defaultChecked":
			case "innerHTML":
			case "ref": break;
			case "autoFocus": break;
			case "xlinkHref":
				if (r == null || typeof r == "function" || typeof r == "boolean" || typeof r == "symbol") {
					e.removeAttribute("xlink:href");
					break;
				}
				n = Ut("" + r), e.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", n);
				break;
			case "contentEditable":
			case "spellCheck":
			case "draggable":
			case "value":
			case "autoReverse":
			case "externalResourcesRequired":
			case "focusable":
			case "preserveAlpha":
				r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, "" + r) : e.removeAttribute(n);
				break;
			case "inert":
			case "allowFullScreen":
			case "async":
			case "autoPlay":
			case "controls":
			case "default":
			case "defer":
			case "disabled":
			case "disablePictureInPicture":
			case "disableRemotePlayback":
			case "formNoValidate":
			case "hidden":
			case "loop":
			case "noModule":
			case "noValidate":
			case "open":
			case "playsInline":
			case "readOnly":
			case "required":
			case "reversed":
			case "scoped":
			case "seamless":
			case "itemScope":
				r && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, "") : e.removeAttribute(n);
				break;
			case "capture":
			case "download":
				!0 === r ? e.setAttribute(n, "") : !1 !== r && r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "cols":
			case "rows":
			case "size":
			case "span":
				r != null && typeof r != "function" && typeof r != "symbol" && !isNaN(r) && 1 <= r ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "rowSpan":
			case "start":
				r == null || typeof r == "function" || typeof r == "symbol" || isNaN(r) ? e.removeAttribute(n) : e.setAttribute(n, r);
				break;
			case "popover":
				$("beforetoggle", e), $("toggle", e), yt(e, "popover", r);
				break;
			case "xlinkActuate":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:actuate", r);
				break;
			case "xlinkArcrole":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:arcrole", r);
				break;
			case "xlinkRole":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:role", r);
				break;
			case "xlinkShow":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:show", r);
				break;
			case "xlinkTitle":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:title", r);
				break;
			case "xlinkType":
				xt(e, "http://www.w3.org/1999/xlink", "xlink:type", r);
				break;
			case "xmlBase":
				xt(e, "http://www.w3.org/XML/1998/namespace", "xml:base", r);
				break;
			case "xmlLang":
				xt(e, "http://www.w3.org/XML/1998/namespace", "xml:lang", r);
				break;
			case "xmlSpace":
				xt(e, "http://www.w3.org/XML/1998/namespace", "xml:space", r);
				break;
			case "is":
				yt(e, "is", r);
				break;
			case "innerText":
			case "textContent": break;
			default: (!(2 < n.length) || n[0] !== "o" && n[0] !== "O" || n[1] !== "n" && n[1] !== "N") && (n = Vt.get(n) || n, yt(e, n, r));
		}
	}
	function Nd(e, t, n, r, i, a) {
		switch (n) {
			case "style":
				zt(e, r, a);
				break;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						e.innerHTML = n;
					}
				}
				break;
			case "children":
				typeof r == "string" ? It(e, r) : (typeof r == "number" || typeof r == "bigint") && It(e, "" + r);
				break;
			case "onScroll":
				r != null && $("scroll", e);
				break;
			case "onScrollEnd":
				r != null && $("scrollend", e);
				break;
			case "onClick":
				r != null && (e.onclick = Wt);
				break;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "innerHTML":
			case "ref": break;
			case "innerText":
			case "textContent": break;
			default: if (!ft.hasOwnProperty(n)) a: {
				if (n[0] === "o" && n[1] === "n" && (i = n.endsWith("Capture"), t = n.slice(2, i ? n.length - 7 : void 0), a = e[Qe] || null, a = a == null ? null : a[n], typeof a == "function" && e.removeEventListener(t, a, i), typeof r == "function")) {
					typeof a != "function" && a !== null && (n in e ? e[n] = null : e.hasAttribute(n) && e.removeAttribute(n)), e.addEventListener(t, r, i);
					break a;
				}
				n in e ? e[n] = r : !0 === r ? e.setAttribute(n, "") : yt(e, n, r);
			}
		}
	}
	function Pd(e, t, n) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "img":
				$("error", e), $("load", e);
				var r = !1, i = !1, a;
				for (a in n) if (n.hasOwnProperty(a)) {
					var o = n[a];
					if (o != null) switch (a) {
						case "src":
							r = !0;
							break;
						case "srcSet":
							i = !0;
							break;
						case "children":
						case "dangerouslySetInnerHTML": throw Error(s(137, t));
						default: Md(e, t, a, o, n, null);
					}
				}
				i && Md(e, t, "srcSet", n.srcSet, n, null), r && Md(e, t, "src", n.src, n, null);
				return;
			case "input":
				$("invalid", e);
				var c = a = o = i = null, l = null, u = null;
				for (r in n) if (n.hasOwnProperty(r)) {
					var d = n[r];
					if (d != null) switch (r) {
						case "name":
							i = d;
							break;
						case "type":
							o = d;
							break;
						case "checked":
							l = d;
							break;
						case "defaultChecked":
							u = d;
							break;
						case "value":
							a = d;
							break;
						case "defaultValue":
							c = d;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (d != null) throw Error(s(137, t));
							break;
						default: Md(e, t, r, d, n, null);
					}
				}
				jt(e, a, c, l, u, o, i, !1);
				return;
			case "select":
				for (i in $("invalid", e), r = o = a = null, n) if (n.hasOwnProperty(i) && (c = n[i], c != null)) switch (i) {
					case "value":
						a = c;
						break;
					case "defaultValue":
						o = c;
						break;
					case "multiple": r = c;
					default: Md(e, t, i, c, n, null);
				}
				t = a, n = o, e.multiple = !!r, t == null ? n != null && Nt(e, !!r, n, !0) : Nt(e, !!r, t, !1);
				return;
			case "textarea":
				for (o in $("invalid", e), a = i = r = null, n) if (n.hasOwnProperty(o) && (c = n[o], c != null)) switch (o) {
					case "value":
						r = c;
						break;
					case "defaultValue":
						i = c;
						break;
					case "children":
						a = c;
						break;
					case "dangerouslySetInnerHTML":
						if (c != null) throw Error(s(91));
						break;
					default: Md(e, t, o, c, n, null);
				}
				Ft(e, r, i, a);
				return;
			case "option":
				for (l in n) if (n.hasOwnProperty(l) && (r = n[l], r != null)) switch (l) {
					case "selected":
						e.selected = r && typeof r != "function" && typeof r != "symbol";
						break;
					default: Md(e, t, l, r, n, null);
				}
				return;
			case "dialog":
				$("beforetoggle", e), $("toggle", e), $("cancel", e), $("close", e);
				break;
			case "iframe":
			case "object":
				$("load", e);
				break;
			case "video":
			case "audio":
				for (r = 0; r < gd.length; r++) $(gd[r], e);
				break;
			case "image":
				$("error", e), $("load", e);
				break;
			case "details":
				$("toggle", e);
				break;
			case "embed":
			case "source":
			case "link": $("error", e), $("load", e);
			case "area":
			case "base":
			case "br":
			case "col":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "track":
			case "wbr":
			case "menuitem":
				for (u in n) if (n.hasOwnProperty(u) && (r = n[u], r != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML": throw Error(s(137, t));
					default: Md(e, t, u, r, n, null);
				}
				return;
			default: if (Bt(t)) {
				for (d in n) n.hasOwnProperty(d) && (r = n[d], r !== void 0 && Nd(e, t, d, r, n, void 0));
				return;
			}
		}
		for (c in n) n.hasOwnProperty(c) && (r = n[c], r != null && Md(e, t, c, r, n, null));
	}
	function Fd(e, t, n, r) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "input":
				var i = null, a = null, o = null, c = null, l = null, u = null, d = null;
				for (m in n) {
					var f = n[m];
					if (n.hasOwnProperty(m) && f != null) switch (m) {
						case "checked": break;
						case "value": break;
						case "defaultValue": l = f;
						default: r.hasOwnProperty(m) || Md(e, t, m, null, r, f);
					}
				}
				for (var p in r) {
					var m = r[p];
					if (f = n[p], r.hasOwnProperty(p) && (m != null || f != null)) switch (p) {
						case "type":
							a = m;
							break;
						case "name":
							i = m;
							break;
						case "checked":
							u = m;
							break;
						case "defaultChecked":
							d = m;
							break;
						case "value":
							o = m;
							break;
						case "defaultValue":
							c = m;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (m != null) throw Error(s(137, t));
							break;
						default: m !== f && Md(e, t, p, m, r, f);
					}
				}
				At(e, o, c, l, u, d, a, i);
				return;
			case "select":
				for (a in m = o = c = p = null, n) if (l = n[a], n.hasOwnProperty(a) && l != null) switch (a) {
					case "value": break;
					case "multiple": m = l;
					default: r.hasOwnProperty(a) || Md(e, t, a, null, r, l);
				}
				for (i in r) if (a = r[i], l = n[i], r.hasOwnProperty(i) && (a != null || l != null)) switch (i) {
					case "value":
						p = a;
						break;
					case "defaultValue":
						c = a;
						break;
					case "multiple": o = a;
					default: a !== l && Md(e, t, i, a, r, l);
				}
				t = c, n = o, r = m, p == null ? !!r != !!n && (t == null ? Nt(e, !!n, n ? [] : "", !1) : Nt(e, !!n, t, !0)) : Nt(e, !!n, p, !1);
				return;
			case "textarea":
				for (c in m = p = null, n) if (i = n[c], n.hasOwnProperty(c) && i != null && !r.hasOwnProperty(c)) switch (c) {
					case "value": break;
					case "children": break;
					default: Md(e, t, c, null, r, i);
				}
				for (o in r) if (i = r[o], a = n[o], r.hasOwnProperty(o) && (i != null || a != null)) switch (o) {
					case "value":
						p = i;
						break;
					case "defaultValue":
						m = i;
						break;
					case "children": break;
					case "dangerouslySetInnerHTML":
						if (i != null) throw Error(s(91));
						break;
					default: i !== a && Md(e, t, o, i, r, a);
				}
				Pt(e, p, m);
				return;
			case "option":
				for (var h in n) if (p = n[h], n.hasOwnProperty(h) && p != null && !r.hasOwnProperty(h)) switch (h) {
					case "selected":
						e.selected = !1;
						break;
					default: Md(e, t, h, null, r, p);
				}
				for (l in r) if (p = r[l], m = n[l], r.hasOwnProperty(l) && p !== m && (p != null || m != null)) switch (l) {
					case "selected":
						e.selected = p && typeof p != "function" && typeof p != "symbol";
						break;
					default: Md(e, t, l, p, r, m);
				}
				return;
			case "img":
			case "link":
			case "area":
			case "base":
			case "br":
			case "col":
			case "embed":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "source":
			case "track":
			case "wbr":
			case "menuitem":
				for (var g in n) p = n[g], n.hasOwnProperty(g) && p != null && !r.hasOwnProperty(g) && Md(e, t, g, null, r, p);
				for (u in r) if (p = r[u], m = n[u], r.hasOwnProperty(u) && p !== m && (p != null || m != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML":
						if (p != null) throw Error(s(137, t));
						break;
					default: Md(e, t, u, p, r, m);
				}
				return;
			default: if (Bt(t)) {
				for (var _ in n) p = n[_], n.hasOwnProperty(_) && p !== void 0 && !r.hasOwnProperty(_) && Nd(e, t, _, void 0, r, p);
				for (d in r) p = r[d], m = n[d], !r.hasOwnProperty(d) || p === m || p === void 0 && m === void 0 || Nd(e, t, d, p, r, m);
				return;
			}
		}
		for (var v in n) p = n[v], n.hasOwnProperty(v) && p != null && !r.hasOwnProperty(v) && Md(e, t, v, null, r, p);
		for (f in r) p = r[f], m = n[f], !r.hasOwnProperty(f) || p === m || p == null && m == null || Md(e, t, f, p, r, m);
	}
	function Id(e) {
		switch (e) {
			case "css":
			case "script":
			case "font":
			case "img":
			case "image":
			case "input":
			case "link": return !0;
			default: return !1;
		}
	}
	function Ld() {
		if (typeof performance.getEntriesByType == "function") {
			for (var e = 0, t = 0, n = performance.getEntriesByType("resource"), r = 0; r < n.length; r++) {
				var i = n[r], a = i.transferSize, o = i.initiatorType, s = i.duration;
				if (a && s && Id(o)) {
					for (o = 0, s = i.responseEnd, r += 1; r < n.length; r++) {
						var c = n[r], l = c.startTime;
						if (l > s) break;
						var u = c.transferSize, d = c.initiatorType;
						u && Id(d) && (c = c.responseEnd, o += u * (c < s ? 1 : (s - l) / (c - l)));
					}
					if (--r, t += 8 * (a + o) / (i.duration / 1e3), e++, 10 < e) break;
				}
			}
			if (0 < e) return t / e / 1e6;
		}
		return navigator.connection && (e = navigator.connection.downlink, typeof e == "number") ? e : 5;
	}
	var Rd = null, zd = null;
	function Bd(e) {
		return e.nodeType === 9 ? e : e.ownerDocument;
	}
	function Vd(e) {
		switch (e) {
			case "http://www.w3.org/2000/svg": return 1;
			case "http://www.w3.org/1998/Math/MathML": return 2;
			default: return 0;
		}
	}
	function Hd(e, t) {
		if (e === 0) switch (t) {
			case "svg": return 1;
			case "math": return 2;
			default: return 0;
		}
		return e === 1 && t === "foreignObject" ? 0 : e;
	}
	function Ud(e, t) {
		return e === "textarea" || e === "noscript" || typeof t.children == "string" || typeof t.children == "number" || typeof t.children == "bigint" || typeof t.dangerouslySetInnerHTML == "object" && t.dangerouslySetInnerHTML !== null && t.dangerouslySetInnerHTML.__html != null;
	}
	var Wd = null;
	function Gd() {
		var e = window.event;
		return e && e.type === "popstate" ? e !== Wd && (Wd = e, !0) : (Wd = null, !1);
	}
	var Kd = typeof setTimeout == "function" ? setTimeout : void 0, qd = typeof clearTimeout == "function" ? clearTimeout : void 0, Jd = typeof Promise == "function" ? Promise : void 0, Yd = typeof queueMicrotask == "function" ? queueMicrotask : Jd === void 0 ? Kd : function(e) {
		return Jd.resolve(null).then(e).catch(Xd);
	};
	function Xd(e) {
		setTimeout(function() {
			throw e;
		});
	}
	function Zd(e) {
		return e === "head";
	}
	function Qd(e, t) {
		var n = t, r = 0;
		do {
			var i = n.nextSibling;
			if (e.removeChild(n), i && i.nodeType === 8) if (n = i.data, n === "/$" || n === "/&") {
				if (r === 0) {
					e.removeChild(i), Np(t);
					return;
				}
				r--;
			} else if (n === "$" || n === "$?" || n === "$~" || n === "$!" || n === "&") r++;
			else if (n === "html") pf(e.ownerDocument.documentElement);
			else if (n === "head") {
				n = e.ownerDocument.head, pf(n);
				for (var a = n.firstChild; a;) {
					var o = a.nextSibling, s = a.nodeName;
					a[it] || s === "SCRIPT" || s === "STYLE" || s === "LINK" && a.rel.toLowerCase() === "stylesheet" || n.removeChild(a), a = o;
				}
			} else n === "body" && pf(e.ownerDocument.body);
			n = i;
		} while (n);
		Np(t);
	}
	function $d(e, t) {
		var n = e;
		e = 0;
		do {
			var r = n.nextSibling;
			if (n.nodeType === 1 ? t ? (n._stashedDisplay = n.style.display, n.style.display = "none") : (n.style.display = n._stashedDisplay || "", n.getAttribute("style") === "" && n.removeAttribute("style")) : n.nodeType === 3 && (t ? (n._stashedText = n.nodeValue, n.nodeValue = "") : n.nodeValue = n._stashedText || ""), r && r.nodeType === 8) if (n = r.data, n === "/$") {
				if (e === 0) break;
				e--;
			} else n !== "$" && n !== "$?" && n !== "$~" && n !== "$!" || e++;
			n = r;
		} while (n);
	}
	function ef(e) {
		var t = e.firstChild;
		for (t && t.nodeType === 10 && (t = t.nextSibling); t;) {
			var n = t;
			switch (t = t.nextSibling, n.nodeName) {
				case "HTML":
				case "HEAD":
				case "BODY":
					ef(n), at(n);
					continue;
				case "SCRIPT":
				case "STYLE": continue;
				case "LINK": if (n.rel.toLowerCase() === "stylesheet") continue;
			}
			e.removeChild(n);
		}
	}
	function tf(e, t, n, r) {
		for (; e.nodeType === 1;) {
			var i = n;
			if (e.nodeName.toLowerCase() !== t.toLowerCase()) {
				if (!r && (e.nodeName !== "INPUT" || e.type !== "hidden")) break;
			} else if (!r) if (t === "input" && e.type === "hidden") {
				var a = i.name == null ? null : "" + i.name;
				if (i.type === "hidden" && e.getAttribute("name") === a) return e;
			} else return e;
			else if (!e[it]) switch (t) {
				case "meta":
					if (!e.hasAttribute("itemprop")) break;
					return e;
				case "link":
					if (a = e.getAttribute("rel"), a === "stylesheet" && e.hasAttribute("data-precedence") || a !== i.rel || e.getAttribute("href") !== (i.href == null || i.href === "" ? null : i.href) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin) || e.getAttribute("title") !== (i.title == null ? null : i.title)) break;
					return e;
				case "style":
					if (e.hasAttribute("data-precedence")) break;
					return e;
				case "script":
					if (a = e.getAttribute("src"), (a !== (i.src == null ? null : i.src) || e.getAttribute("type") !== (i.type == null ? null : i.type) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin)) && a && e.hasAttribute("async") && !e.hasAttribute("itemprop")) break;
					return e;
				default: return e;
			}
			if (e = cf(e.nextSibling), e === null) break;
		}
		return null;
	}
	function nf(e, t, n) {
		if (t === "") return null;
		for (; e.nodeType !== 3;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !n || (e = cf(e.nextSibling), e === null)) return null;
		return e;
	}
	function rf(e, t) {
		for (; e.nodeType !== 8;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !t || (e = cf(e.nextSibling), e === null)) return null;
		return e;
	}
	function af(e) {
		return e.data === "$?" || e.data === "$~";
	}
	function of(e) {
		return e.data === "$!" || e.data === "$?" && e.ownerDocument.readyState !== "loading";
	}
	function sf(e, t) {
		var n = e.ownerDocument;
		if (e.data === "$~") e._reactRetry = t;
		else if (e.data !== "$?" || n.readyState !== "loading") t();
		else {
			var r = function() {
				t(), n.removeEventListener("DOMContentLoaded", r);
			};
			n.addEventListener("DOMContentLoaded", r), e._reactRetry = r;
		}
	}
	function cf(e) {
		for (; e != null; e = e.nextSibling) {
			var t = e.nodeType;
			if (t === 1 || t === 3) break;
			if (t === 8) {
				if (t = e.data, t === "$" || t === "$!" || t === "$?" || t === "$~" || t === "&" || t === "F!" || t === "F") break;
				if (t === "/$" || t === "/&") return null;
			}
		}
		return e;
	}
	var lf = null;
	function uf(e) {
		e = e.nextSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "/$" || n === "/&") {
					if (t === 0) return cf(e.nextSibling);
					t--;
				} else n !== "$" && n !== "$!" && n !== "$?" && n !== "$~" && n !== "&" || t++;
			}
			e = e.nextSibling;
		}
		return null;
	}
	function df(e) {
		e = e.previousSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "$" || n === "$!" || n === "$?" || n === "$~" || n === "&") {
					if (t === 0) return e;
					t--;
				} else n !== "/$" && n !== "/&" || t++;
			}
			e = e.previousSibling;
		}
		return null;
	}
	function ff(e, t, n) {
		switch (t = Bd(n), e) {
			case "html":
				if (e = t.documentElement, !e) throw Error(s(452));
				return e;
			case "head":
				if (e = t.head, !e) throw Error(s(453));
				return e;
			case "body":
				if (e = t.body, !e) throw Error(s(454));
				return e;
			default: throw Error(s(451));
		}
	}
	function pf(e) {
		for (var t = e.attributes; t.length;) e.removeAttributeNode(t[0]);
		at(e);
	}
	var mf = /* @__PURE__ */ new Map(), hf = /* @__PURE__ */ new Set();
	function gf(e) {
		return typeof e.getRootNode == "function" ? e.getRootNode() : e.nodeType === 9 ? e : e.ownerDocument;
	}
	var _f = L.d;
	L.d = {
		f: vf,
		r: yf,
		D: Sf,
		C: Cf,
		L: wf,
		m: Tf,
		X: Df,
		S: Ef,
		M: Of
	};
	function vf() {
		var e = _f.f(), t = vu();
		return e || t;
	}
	function yf(e) {
		var t = st(e);
		t !== null && t.tag === 5 && t.type === "form" ? ys(t) : _f.r(e);
	}
	var bf = typeof document > "u" ? null : document;
	function xf(e, t, n) {
		var r = bf;
		if (r && typeof t == "string" && t) {
			var i = kt(t);
			i = "link[rel=\"" + e + "\"][href=\"" + i + "\"]", typeof n == "string" && (i += "[crossorigin=\"" + n + "\"]"), hf.has(i) || (hf.add(i), e = {
				rel: e,
				crossOrigin: n,
				href: t
			}, r.querySelector(i) === null && (t = r.createElement("link"), Pd(t, "link", e), ut(t), r.head.appendChild(t)));
		}
	}
	function Sf(e) {
		_f.D(e), xf("dns-prefetch", e, null);
	}
	function Cf(e, t) {
		_f.C(e, t), xf("preconnect", e, t);
	}
	function wf(e, t, n) {
		_f.L(e, t, n);
		var r = bf;
		if (r && e && t) {
			var i = "link[rel=\"preload\"][as=\"" + kt(t) + "\"]";
			t === "image" && n && n.imageSrcSet ? (i += "[imagesrcset=\"" + kt(n.imageSrcSet) + "\"]", typeof n.imageSizes == "string" && (i += "[imagesizes=\"" + kt(n.imageSizes) + "\"]")) : i += "[href=\"" + kt(e) + "\"]";
			var a = i;
			switch (t) {
				case "style":
					a = Af(e);
					break;
				case "script": a = Pf(e);
			}
			mf.has(a) || (e = h({
				rel: "preload",
				href: t === "image" && n && n.imageSrcSet ? void 0 : e,
				as: t
			}, n), mf.set(a, e), r.querySelector(i) !== null || t === "style" && r.querySelector(jf(a)) || t === "script" && r.querySelector(Ff(a)) || (t = r.createElement("link"), Pd(t, "link", e), ut(t), r.head.appendChild(t)));
		}
	}
	function Tf(e, t) {
		_f.m(e, t);
		var n = bf;
		if (n && e) {
			var r = t && typeof t.as == "string" ? t.as : "script", i = "link[rel=\"modulepreload\"][as=\"" + kt(r) + "\"][href=\"" + kt(e) + "\"]", a = i;
			switch (r) {
				case "audioworklet":
				case "paintworklet":
				case "serviceworker":
				case "sharedworker":
				case "worker":
				case "script": a = Pf(e);
			}
			if (!mf.has(a) && (e = h({
				rel: "modulepreload",
				href: e
			}, t), mf.set(a, e), n.querySelector(i) === null)) {
				switch (r) {
					case "audioworklet":
					case "paintworklet":
					case "serviceworker":
					case "sharedworker":
					case "worker":
					case "script": if (n.querySelector(Ff(a))) return;
				}
				r = n.createElement("link"), Pd(r, "link", e), ut(r), n.head.appendChild(r);
			}
		}
	}
	function Ef(e, t, n) {
		_f.S(e, t, n);
		var r = bf;
		if (r && e) {
			var i = lt(r).hoistableStyles, a = Af(e);
			t ||= "default";
			var o = i.get(a);
			if (!o) {
				var s = {
					loading: 0,
					preload: null
				};
				if (o = r.querySelector(jf(a))) s.loading = 5;
				else {
					e = h({
						rel: "stylesheet",
						href: e,
						"data-precedence": t
					}, n), (n = mf.get(a)) && Rf(e, n);
					var c = o = r.createElement("link");
					ut(c), Pd(c, "link", e), c._p = new Promise(function(e, t) {
						c.onload = e, c.onerror = t;
					}), c.addEventListener("load", function() {
						s.loading |= 1;
					}), c.addEventListener("error", function() {
						s.loading |= 2;
					}), s.loading |= 4, Lf(o, t, r);
				}
				o = {
					type: "stylesheet",
					instance: o,
					count: 1,
					state: s
				}, i.set(a, o);
			}
		}
	}
	function Df(e, t) {
		_f.X(e, t);
		var n = bf;
		if (n && e) {
			var r = lt(n).hoistableScripts, i = Pf(e), a = r.get(i);
			a || (a = n.querySelector(Ff(i)), a || (e = h({
				src: e,
				async: !0
			}, t), (t = mf.get(i)) && zf(e, t), a = n.createElement("script"), ut(a), Pd(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function Of(e, t) {
		_f.M(e, t);
		var n = bf;
		if (n && e) {
			var r = lt(n).hoistableScripts, i = Pf(e), a = r.get(i);
			a || (a = n.querySelector(Ff(i)), a || (e = h({
				src: e,
				async: !0,
				type: "module"
			}, t), (t = mf.get(i)) && zf(e, t), a = n.createElement("script"), ut(a), Pd(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function kf(e, t, n, r) {
		var i = (i = W.current) ? gf(i) : null;
		if (!i) throw Error(s(446));
		switch (e) {
			case "meta":
			case "title": return null;
			case "style": return typeof n.precedence == "string" && typeof n.href == "string" ? (t = Af(n.href), n = lt(i).hoistableStyles, r = n.get(t), r || (r = {
				type: "style",
				instance: null,
				count: 0,
				state: null
			}, n.set(t, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			case "link":
				if (n.rel === "stylesheet" && typeof n.href == "string" && typeof n.precedence == "string") {
					e = Af(n.href);
					var a = lt(i).hoistableStyles, o = a.get(e);
					if (o || (i = i.ownerDocument || i, o = {
						type: "stylesheet",
						instance: null,
						count: 0,
						state: {
							loading: 0,
							preload: null
						}
					}, a.set(e, o), (a = i.querySelector(jf(e))) && !a._p && (o.instance = a, o.state.loading = 5), mf.has(e) || (n = {
						rel: "preload",
						as: "style",
						href: n.href,
						crossOrigin: n.crossOrigin,
						integrity: n.integrity,
						media: n.media,
						hrefLang: n.hrefLang,
						referrerPolicy: n.referrerPolicy
					}, mf.set(e, n), a || Nf(i, e, n, o.state))), t && r === null) throw Error(s(528, ""));
					return o;
				}
				if (t && r !== null) throw Error(s(529, ""));
				return null;
			case "script": return t = n.async, n = n.src, typeof n == "string" && t && typeof t != "function" && typeof t != "symbol" ? (t = Pf(n), n = lt(i).hoistableScripts, r = n.get(t), r || (r = {
				type: "script",
				instance: null,
				count: 0,
				state: null
			}, n.set(t, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			default: throw Error(s(444, e));
		}
	}
	function Af(e) {
		return "href=\"" + kt(e) + "\"";
	}
	function jf(e) {
		return "link[rel=\"stylesheet\"][" + e + "]";
	}
	function Mf(e) {
		return h({}, e, {
			"data-precedence": e.precedence,
			precedence: null
		});
	}
	function Nf(e, t, n, r) {
		e.querySelector("link[rel=\"preload\"][as=\"style\"][" + t + "]") ? r.loading = 1 : (t = e.createElement("link"), r.preload = t, t.addEventListener("load", function() {
			return r.loading |= 1;
		}), t.addEventListener("error", function() {
			return r.loading |= 2;
		}), Pd(t, "link", n), ut(t), e.head.appendChild(t));
	}
	function Pf(e) {
		return "[src=\"" + kt(e) + "\"]";
	}
	function Ff(e) {
		return "script[async]" + e;
	}
	function If(e, t, n) {
		if (t.count++, t.instance === null) switch (t.type) {
			case "style":
				var r = e.querySelector("style[data-href~=\"" + kt(n.href) + "\"]");
				if (r) return t.instance = r, ut(r), r;
				var i = h({}, n, {
					"data-href": n.href,
					"data-precedence": n.precedence,
					href: null,
					precedence: null
				});
				return r = (e.ownerDocument || e).createElement("style"), ut(r), Pd(r, "style", i), Lf(r, n.precedence, e), t.instance = r;
			case "stylesheet":
				i = Af(n.href);
				var a = e.querySelector(jf(i));
				if (a) return t.state.loading |= 4, t.instance = a, ut(a), a;
				r = Mf(n), (i = mf.get(i)) && Rf(r, i), a = (e.ownerDocument || e).createElement("link"), ut(a);
				var o = a;
				return o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), Pd(a, "link", r), t.state.loading |= 4, Lf(a, n.precedence, e), t.instance = a;
			case "script": return a = Pf(n.src), (i = e.querySelector(Ff(a))) ? (t.instance = i, ut(i), i) : (r = n, (i = mf.get(a)) && (r = h({}, n), zf(r, i)), e = e.ownerDocument || e, i = e.createElement("script"), ut(i), Pd(i, "link", r), e.head.appendChild(i), t.instance = i);
			case "void": return null;
			default: throw Error(s(443, t.type));
		}
		else t.type === "stylesheet" && !(t.state.loading & 4) && (r = t.instance, t.state.loading |= 4, Lf(r, n.precedence, e));
		return t.instance;
	}
	function Lf(e, t, n) {
		for (var r = n.querySelectorAll("link[rel=\"stylesheet\"][data-precedence],style[data-precedence]"), i = r.length ? r[r.length - 1] : null, a = i, o = 0; o < r.length; o++) {
			var s = r[o];
			if (s.dataset.precedence === t) a = s;
			else if (a !== i) break;
		}
		a ? a.parentNode.insertBefore(e, a.nextSibling) : (t = n.nodeType === 9 ? n.head : n, t.insertBefore(e, t.firstChild));
	}
	function Rf(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.title ??= t.title;
	}
	function zf(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.integrity ??= t.integrity;
	}
	var Bf = null;
	function Vf(e, t, n) {
		if (Bf === null) {
			var r = /* @__PURE__ */ new Map(), i = Bf = /* @__PURE__ */ new Map();
			i.set(n, r);
		} else i = Bf, r = i.get(n), r || (r = /* @__PURE__ */ new Map(), i.set(n, r));
		if (r.has(e)) return r;
		for (r.set(e, null), n = n.getElementsByTagName(e), i = 0; i < n.length; i++) {
			var a = n[i];
			if (!(a[it] || a[Ze] || e === "link" && a.getAttribute("rel") === "stylesheet") && a.namespaceURI !== "http://www.w3.org/2000/svg") {
				var o = a.getAttribute(t) || "";
				o = e + o;
				var s = r.get(o);
				s ? s.push(a) : r.set(o, [a]);
			}
		}
		return r;
	}
	function Hf(e, t, n) {
		e = e.ownerDocument || e, e.head.insertBefore(n, t === "title" ? e.querySelector("head > title") : null);
	}
	function Uf(e, t, n) {
		if (n === 1 || t.itemProp != null) return !1;
		switch (e) {
			case "meta":
			case "title": return !0;
			case "style":
				if (typeof t.precedence != "string" || typeof t.href != "string" || t.href === "") break;
				return !0;
			case "link":
				if (typeof t.rel != "string" || typeof t.href != "string" || t.href === "" || t.onLoad || t.onError) break;
				switch (t.rel) {
					case "stylesheet": return e = t.disabled, typeof t.precedence == "string" && e == null;
					default: return !0;
				}
			case "script": if (t.async && typeof t.async != "function" && typeof t.async != "symbol" && !t.onLoad && !t.onError && t.src && typeof t.src == "string") return !0;
		}
		return !1;
	}
	function Wf(e) {
		return !(e.type === "stylesheet" && !(e.state.loading & 3));
	}
	function Gf(e, t, n, r) {
		if (n.type === "stylesheet" && (typeof r.media != "string" || !1 !== matchMedia(r.media).matches) && !(n.state.loading & 4)) {
			if (n.instance === null) {
				var i = Af(r.href), a = t.querySelector(jf(i));
				if (a) {
					t = a._p, typeof t == "object" && t && typeof t.then == "function" && (e.count++, e = Jf.bind(e), t.then(e, e)), n.state.loading |= 4, n.instance = a, ut(a);
					return;
				}
				a = t.ownerDocument || t, r = Mf(r), (i = mf.get(i)) && Rf(r, i), a = a.createElement("link"), ut(a);
				var o = a;
				o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), Pd(a, "link", r), n.instance = a;
			}
			e.stylesheets === null && (e.stylesheets = /* @__PURE__ */ new Map()), e.stylesheets.set(n, t), (t = n.state.preload) && !(n.state.loading & 3) && (e.count++, n = Jf.bind(e), t.addEventListener("load", n), t.addEventListener("error", n));
		}
	}
	var Kf = 0;
	function qf(e, t) {
		return e.stylesheets && e.count === 0 && Xf(e, e.stylesheets), 0 < e.count || 0 < e.imgCount ? function(n) {
			var r = setTimeout(function() {
				if (e.stylesheets && Xf(e, e.stylesheets), e.unsuspend) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, 6e4 + t);
			0 < e.imgBytes && Kf === 0 && (Kf = 62500 * Ld());
			var i = setTimeout(function() {
				if (e.waitingForImages = !1, e.count === 0 && (e.stylesheets && Xf(e, e.stylesheets), e.unsuspend)) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, (e.imgBytes > Kf ? 50 : 800) + t);
			return e.unsuspend = n, function() {
				e.unsuspend = null, clearTimeout(r), clearTimeout(i);
			};
		} : null;
	}
	function Jf() {
		if (this.count--, this.count === 0 && (this.imgCount === 0 || !this.waitingForImages)) {
			if (this.stylesheets) Xf(this, this.stylesheets);
			else if (this.unsuspend) {
				var e = this.unsuspend;
				this.unsuspend = null, e();
			}
		}
	}
	var Yf = null;
	function Xf(e, t) {
		e.stylesheets = null, e.unsuspend !== null && (e.count++, Yf = /* @__PURE__ */ new Map(), t.forEach(Zf, e), Yf = null, Jf.call(e));
	}
	function Zf(e, t) {
		if (!(t.state.loading & 4)) {
			var n = Yf.get(e);
			if (n) var r = n.get(null);
			else {
				n = /* @__PURE__ */ new Map(), Yf.set(e, n);
				for (var i = e.querySelectorAll("link[data-precedence],style[data-precedence]"), a = 0; a < i.length; a++) {
					var o = i[a];
					(o.nodeName === "LINK" || o.getAttribute("media") !== "not all") && (n.set(o.dataset.precedence, o), r = o);
				}
				r && n.set(null, r);
			}
			i = t.instance, o = i.getAttribute("data-precedence"), a = n.get(o) || r, a === r && n.set(null, i), n.set(o, i), this.count++, r = Jf.bind(this), i.addEventListener("load", r), i.addEventListener("error", r), a ? a.parentNode.insertBefore(i, a.nextSibling) : (e = e.nodeType === 9 ? e.head : e, e.insertBefore(i, e.firstChild)), t.state.loading |= 4;
		}
	}
	var Qf = {
		$$typeof: C,
		Provider: null,
		Consumer: null,
		_currentValue: R,
		_currentValue2: R,
		_threadCount: 0
	};
	function $f(e, t, n, r, i, a, o, s, c) {
		this.tag = 1, this.containerInfo = e, this.pingCache = this.current = this.pendingChildren = null, this.timeoutHandle = -1, this.callbackNode = this.next = this.pendingContext = this.context = this.cancelPendingCommit = null, this.callbackPriority = 0, this.expirationTimes = Be(-1), this.entangledLanes = this.shellSuspendCounter = this.errorRecoveryDisabledLanes = this.expiredLanes = this.warmLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0, this.entanglements = Be(0), this.hiddenUpdates = Be(null), this.identifierPrefix = r, this.onUncaughtError = i, this.onCaughtError = a, this.onRecoverableError = o, this.pooledCache = null, this.pooledCacheLanes = 0, this.formState = c, this.incompleteTransitions = /* @__PURE__ */ new Map();
	}
	function ep(e, t, n, r, i, a, o, s, c, l, u, d) {
		return e = new $f(e, t, n, o, c, l, u, d, s), t = 1, !0 === a && (t |= 24), a = Qr(3, null, null, t), e.current = a, a.stateNode = e, t = $i(), t.refCount++, e.pooledCache = t, t.refCount++, a.memoizedState = {
			element: r,
			isDehydrated: n,
			cache: t
		}, Ma(a), e;
	}
	function tp(e) {
		return e ? (e = Xr, e) : Xr;
	}
	function np(e, t, n, r, i, a) {
		i = tp(i), r.context === null ? r.context = i : r.pendingContext = i, r = Pa(t), r.payload = { element: n }, a = a === void 0 ? null : a, a !== null && (r.callback = a), n = Fa(e, r, t), n !== null && (pu(n, e, t), Ia(n, e, t));
	}
	function rp(e, t) {
		if (e = e.memoizedState, e !== null && e.dehydrated !== null) {
			var n = e.retryLane;
			e.retryLane = n !== 0 && n < t ? n : t;
		}
	}
	function ip(e, t) {
		rp(e, t), (e = e.alternate) && rp(e, t);
	}
	function ap(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = qr(e, 67108864);
			t !== null && pu(t, e, 67108864), ip(e, 67108864);
		}
	}
	function op(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = du();
			t = Ke(t);
			var n = qr(e, t);
			n !== null && pu(n, e, t), ip(e, t);
		}
	}
	var sp = !0;
	function cp(e, t, n, r) {
		var i = I.T;
		I.T = null;
		var a = L.p;
		try {
			L.p = 2, up(e, t, n, r);
		} finally {
			L.p = a, I.T = i;
		}
	}
	function lp(e, t, n, r) {
		var i = I.T;
		I.T = null;
		var a = L.p;
		try {
			L.p = 8, up(e, t, n, r);
		} finally {
			L.p = a, I.T = i;
		}
	}
	function up(e, t, n, r) {
		if (sp) {
			var i = dp(r);
			if (i === null) Cd(e, t, r, fp, n), Cp(e, r);
			else if (Tp(i, e, t, n, r)) r.stopPropagation();
			else if (Cp(e, r), t & 4 && -1 < Sp.indexOf(e)) {
				for (; i !== null;) {
					var a = st(i);
					if (a !== null) switch (a.tag) {
						case 3:
							if (a = a.stateNode, a.current.memoizedState.isDehydrated) {
								var o = Fe(a.pendingLanes);
								if (o !== 0) {
									var s = a;
									for (s.pendingLanes |= 2, s.entangledLanes |= 2; o;) {
										var c = 1 << 31 - Oe(o);
										s.entanglements[1] |= c, o &= ~c;
									}
									nd(a), !(Pl & 6) && ($l = ge() + 500, rd(0, !1));
								}
							}
							break;
						case 31:
						case 13: s = qr(a, 2), s !== null && pu(s, a, 2), vu(), ip(a, 2);
					}
					if (a = dp(r), a === null && Cd(e, t, r, fp, n), a === i) break;
					i = a;
				}
				i !== null && r.stopPropagation();
			} else Cd(e, t, r, null, n);
		}
	}
	function dp(e) {
		return e = Kt(e), pp(e);
	}
	var fp = null;
	function pp(e) {
		if (fp = null, e = ot(e), e !== null) {
			var t = l(e);
			if (t === null) e = null;
			else {
				var n = t.tag;
				if (n === 13) {
					if (e = u(t), e !== null) return e;
					e = null;
				} else if (n === 31) {
					if (e = d(t), e !== null) return e;
					e = null;
				} else if (n === 3) {
					if (t.stateNode.current.memoizedState.isDehydrated) return t.tag === 3 ? t.stateNode.containerInfo : null;
					e = null;
				} else t !== e && (e = null);
			}
		}
		return fp = e, null;
	}
	function mp(e) {
		switch (e) {
			case "beforetoggle":
			case "cancel":
			case "click":
			case "close":
			case "contextmenu":
			case "copy":
			case "cut":
			case "auxclick":
			case "dblclick":
			case "dragend":
			case "dragstart":
			case "drop":
			case "focusin":
			case "focusout":
			case "input":
			case "invalid":
			case "keydown":
			case "keypress":
			case "keyup":
			case "mousedown":
			case "mouseup":
			case "paste":
			case "pause":
			case "play":
			case "pointercancel":
			case "pointerdown":
			case "pointerup":
			case "ratechange":
			case "reset":
			case "resize":
			case "seeked":
			case "submit":
			case "toggle":
			case "touchcancel":
			case "touchend":
			case "touchstart":
			case "volumechange":
			case "change":
			case "selectionchange":
			case "textInput":
			case "compositionstart":
			case "compositionend":
			case "compositionupdate":
			case "beforeblur":
			case "afterblur":
			case "beforeinput":
			case "blur":
			case "fullscreenchange":
			case "focus":
			case "hashchange":
			case "popstate":
			case "select":
			case "selectstart": return 2;
			case "drag":
			case "dragenter":
			case "dragexit":
			case "dragleave":
			case "dragover":
			case "mousemove":
			case "mouseout":
			case "mouseover":
			case "pointermove":
			case "pointerout":
			case "pointerover":
			case "scroll":
			case "touchmove":
			case "wheel":
			case "mouseenter":
			case "mouseleave":
			case "pointerenter":
			case "pointerleave": return 8;
			case "message": switch (_e()) {
				case ve: return 2;
				case ye: return 8;
				case be:
				case xe: return 32;
				case Se: return 268435456;
				default: return 32;
			}
			default: return 32;
		}
	}
	var hp = !1, gp = null, _p = null, vp = null, yp = /* @__PURE__ */ new Map(), bp = /* @__PURE__ */ new Map(), xp = [], Sp = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset".split(" ");
	function Cp(e, t) {
		switch (e) {
			case "focusin":
			case "focusout":
				gp = null;
				break;
			case "dragenter":
			case "dragleave":
				_p = null;
				break;
			case "mouseover":
			case "mouseout":
				vp = null;
				break;
			case "pointerover":
			case "pointerout":
				yp.delete(t.pointerId);
				break;
			case "gotpointercapture":
			case "lostpointercapture": bp.delete(t.pointerId);
		}
	}
	function wp(e, t, n, r, i, a) {
		return e === null || e.nativeEvent !== a ? (e = {
			blockedOn: t,
			domEventName: n,
			eventSystemFlags: r,
			nativeEvent: a,
			targetContainers: [i]
		}, t !== null && (t = st(t), t !== null && ap(t)), e) : (e.eventSystemFlags |= r, t = e.targetContainers, i !== null && t.indexOf(i) === -1 && t.push(i), e);
	}
	function Tp(e, t, n, r, i) {
		switch (t) {
			case "focusin": return gp = wp(gp, e, t, n, r, i), !0;
			case "dragenter": return _p = wp(_p, e, t, n, r, i), !0;
			case "mouseover": return vp = wp(vp, e, t, n, r, i), !0;
			case "pointerover":
				var a = i.pointerId;
				return yp.set(a, wp(yp.get(a) || null, e, t, n, r, i)), !0;
			case "gotpointercapture": return a = i.pointerId, bp.set(a, wp(bp.get(a) || null, e, t, n, r, i)), !0;
		}
		return !1;
	}
	function Ep(e) {
		var t = ot(e.target);
		if (t !== null) {
			var n = l(t);
			if (n !== null) {
				if (t = n.tag, t === 13) {
					if (t = u(n), t !== null) {
						e.blockedOn = t, Ye(e.priority, function() {
							op(n);
						});
						return;
					}
				} else if (t === 31) {
					if (t = d(n), t !== null) {
						e.blockedOn = t, Ye(e.priority, function() {
							op(n);
						});
						return;
					}
				} else if (t === 3 && n.stateNode.current.memoizedState.isDehydrated) {
					e.blockedOn = n.tag === 3 ? n.stateNode.containerInfo : null;
					return;
				}
			}
		}
		e.blockedOn = null;
	}
	function Dp(e) {
		if (e.blockedOn !== null) return !1;
		for (var t = e.targetContainers; 0 < t.length;) {
			var n = dp(e.nativeEvent);
			if (n === null) {
				n = e.nativeEvent;
				var r = new n.constructor(n.type, n);
				Gt = r, n.target.dispatchEvent(r), Gt = null;
			} else return t = st(n), t !== null && ap(t), e.blockedOn = n, !1;
			t.shift();
		}
		return !0;
	}
	function Op(e, t, n) {
		Dp(e) && n.delete(t);
	}
	function kp() {
		hp = !1, gp !== null && Dp(gp) && (gp = null), _p !== null && Dp(_p) && (_p = null), vp !== null && Dp(vp) && (vp = null), yp.forEach(Op), bp.forEach(Op);
	}
	function Ap(e, n) {
		e.blockedOn === n && (e.blockedOn = null, hp || (hp = !0, t.unstable_scheduleCallback(t.unstable_NormalPriority, kp)));
	}
	var jp = null;
	function Mp(e) {
		jp !== e && (jp = e, t.unstable_scheduleCallback(t.unstable_NormalPriority, function() {
			jp === e && (jp = null);
			for (var t = 0; t < e.length; t += 3) {
				var n = e[t], r = e[t + 1], i = e[t + 2];
				if (typeof r != "function") {
					if (pp(r || n) === null) continue;
					break;
				}
				var a = st(n);
				a !== null && (e.splice(t, 3), t -= 3, _s(a, {
					pending: !0,
					data: i,
					method: n.method,
					action: r
				}, r, i));
			}
		}));
	}
	function Np(e) {
		function t(t) {
			return Ap(t, e);
		}
		gp !== null && Ap(gp, e), _p !== null && Ap(_p, e), vp !== null && Ap(vp, e), yp.forEach(t), bp.forEach(t);
		for (var n = 0; n < xp.length; n++) {
			var r = xp[n];
			r.blockedOn === e && (r.blockedOn = null);
		}
		for (; 0 < xp.length && (n = xp[0], n.blockedOn === null);) Ep(n), n.blockedOn === null && xp.shift();
		if (n = (e.ownerDocument || e).$$reactFormReplay, n != null) for (r = 0; r < n.length; r += 3) {
			var i = n[r], a = n[r + 1], o = i[Qe] || null;
			if (typeof a == "function") o || Mp(n);
			else if (o) {
				var s = null;
				if (a && a.hasAttribute("formAction")) {
					if (i = a, o = a[Qe] || null) s = o.formAction;
					else if (pp(i) !== null) continue;
				} else s = o.action;
				typeof s == "function" ? n[r + 1] = s : (n.splice(r, 3), r -= 3), Mp(n);
			}
		}
	}
	function Pp() {
		function e(e) {
			e.canIntercept && e.info === "react-transition" && e.intercept({
				handler: function() {
					return new Promise(function(e) {
						return i = e;
					});
				},
				focusReset: "manual",
				scroll: "manual"
			});
		}
		function t() {
			i !== null && (i(), i = null), r || setTimeout(n, 20);
		}
		function n() {
			if (!r && !navigation.transition) {
				var e = navigation.currentEntry;
				e && e.url != null && navigation.navigate(e.url, {
					state: e.getState(),
					info: "react-transition",
					history: "replace"
				});
			}
		}
		if (typeof navigation == "object") {
			var r = !1, i = null;
			return navigation.addEventListener("navigate", e), navigation.addEventListener("navigatesuccess", t), navigation.addEventListener("navigateerror", t), setTimeout(n, 100), function() {
				r = !0, navigation.removeEventListener("navigate", e), navigation.removeEventListener("navigatesuccess", t), navigation.removeEventListener("navigateerror", t), i !== null && (i(), i = null);
			};
		}
	}
	function Fp(e) {
		this._internalRoot = e;
	}
	Ip.prototype.render = Fp.prototype.render = function(e) {
		var t = this._internalRoot;
		if (t === null) throw Error(s(409));
		var n = t.current;
		np(n, du(), e, t, null, null);
	}, Ip.prototype.unmount = Fp.prototype.unmount = function() {
		var e = this._internalRoot;
		if (e !== null) {
			this._internalRoot = null;
			var t = e.containerInfo;
			np(e.current, 2, null, e, null, null), vu(), t[$e] = null;
		}
	};
	function Ip(e) {
		this._internalRoot = e;
	}
	Ip.prototype.unstable_scheduleHydration = function(e) {
		if (e) {
			var t = Je();
			e = {
				blockedOn: null,
				target: e,
				priority: t
			};
			for (var n = 0; n < xp.length && t !== 0 && t < xp[n].priority; n++);
			xp.splice(n, 0, e), n === 0 && Ep(e);
		}
	};
	var Lp = r.version;
	if (Lp !== "19.2.8") throw Error(s(527, Lp, "19.2.8"));
	L.findDOMNode = function(e) {
		var t = e._reactInternals;
		if (t === void 0) throw typeof e.render == "function" ? Error(s(188)) : (e = Object.keys(e).join(","), Error(s(268, e)));
		return e = p(t), e = e === null ? null : m(e), e = e === null ? null : e.stateNode, e;
	};
	var Rp = {
		bundleType: 0,
		version: "19.2.8",
		rendererPackageName: "react-dom",
		currentDispatcherRef: I,
		reconcilerVersion: "19.2.8"
	};
	if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
		var zp = __REACT_DEVTOOLS_GLOBAL_HOOK__;
		if (!zp.isDisabled && zp.supportsFiber) try {
			Te = zp.inject(Rp), Ee = zp;
		} catch {}
	}
	e.createRoot = function(e, t) {
		if (!c(e)) throw Error(s(299));
		var n = !1, r = "", i = Bs, a = Vs, o = Hs;
		return t != null && (!0 === t.unstable_strictMode && (n = !0), t.identifierPrefix !== void 0 && (r = t.identifierPrefix), t.onUncaughtError !== void 0 && (i = t.onUncaughtError), t.onCaughtError !== void 0 && (a = t.onCaughtError), t.onRecoverableError !== void 0 && (o = t.onRecoverableError)), t = ep(e, 1, !1, null, null, n, r, null, i, a, o, Pp), e[$e] = t.current, xd(e), new Fp(t);
	};
})), c = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function")) try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = s();
})), l = n(), u = c(), d = {
	us: "US",
	kr: "KR",
	europe: "EU",
	jp: "JP",
	US: "US",
	KR: "KR",
	EUROPE: "EU",
	JP: "JP"
}, f = {
	us: "미국",
	kr: "한국",
	europe: "유럽",
	jp: "일본",
	US: "미국",
	KR: "한국",
	EUROPE: "유럽",
	JP: "일본"
}, p = "rules_on_engine_failure", m = /* @__PURE__ */ "id.jobId.category.kind.taskType.labelCode.status.progress.messageCode.createdAt.startedAt.updatedAt.finishedAt.errorCode.generationMode.adapter.requestedMode.mode.attemptedEngine.finalEngine.fallbackReason.artifactTypes.artifactCount.proposalId.proposalStatus.resultStatus".split("."), h = [
	"schemaVersion",
	"storeRevision",
	"jobsStoreRevision",
	"retention",
	"total",
	"entries"
], g = ["maxEntries", "maxDays"], _ = /* @__PURE__ */ new Set(["companion", "task"]), v = /* @__PURE__ */ new Set([
	"index",
	"rss",
	"setup",
	"agent_bridge",
	"agent_cli_install",
	"briefing",
	"company_analysis",
	"topic_report",
	"market_state_snapshot"
]), y = /* @__PURE__ */ new Set([
	"index",
	"rss",
	"setup",
	"companion",
	"briefing",
	"company_analysis",
	"topic_report",
	"personal_overlay",
	"thesis_delta",
	"market_memory_llm",
	"market_state_snapshot",
	"market_memory_update",
	"quality_repair",
	"investment_review"
]), b = /* @__PURE__ */ new Set([
	"index_rebuild",
	"rss_import",
	"setup",
	"agent_chat",
	"agent_cli_install",
	"agent_task",
	"briefing",
	"company_analysis",
	"topic_report",
	"market_state"
]), x = /* @__PURE__ */ new Set([
	"queued",
	"running",
	"cancel_requested",
	"committing",
	"done",
	"cancelled",
	"failed",
	"failed_cancel",
	"failed_commit",
	"failed_restart",
	"failed_commit_recovery"
]), S = /* @__PURE__ */ new Set([
	"llm_api",
	"llm_cli",
	"rules",
	"none"
]), C = /* @__PURE__ */ new Set([
	"auto",
	"codex",
	"claude",
	"antigravity",
	"openai_api",
	"gemini_api",
	"claude_api",
	"rules",
	"none"
]), w = /* @__PURE__ */ new Set(["direct", "cli"]), T = /* @__PURE__ */ new Set([
	"collect",
	"index",
	"install",
	"answer",
	"generate",
	"revise",
	"fallback"
]), E = /* @__PURE__ */ new Set([
	"api",
	"cli",
	"rules",
	"none"
]), D = /* @__PURE__ */ new Set([
	"engine_unavailable",
	"engine_failed",
	"confirmed_zero_evidence"
]), O = /* @__PURE__ */ new Set([
	"adapter_unavailable",
	"adapter_failed",
	"validation_failed",
	"save_failed",
	"cancel_failed",
	"restart_interrupted",
	"commit_recovery_failed",
	"private_cleanup_failed",
	"store_unavailable",
	"internal_error"
]), k = /* @__PURE__ */ new Set([
	"pending",
	"applying",
	"applied",
	"rejected",
	"stale",
	"conflict",
	"failed_apply",
	"unavailable"
]), A = /* @__PURE__ */ new Set([
	"done",
	"cancelled",
	"failed"
]), j = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;
function M(e, t) {
	if (!L(e)) return !1;
	let n = Object.keys(e).sort(), r = [...t].sort();
	return n.length === r.length && n.every((e, t) => e === r[t]);
}
function N(e) {
	if (!M(e, m)) return !1;
	let t = (e, t) => e === null || t.has(e), n = (e) => e === null || typeof e == "string" && j.test(e);
	return typeof e.id == "string" && /^wl_[0-9a-f]{24}$/.test(e.id) && typeof e.jobId == "string" && _.has(e.category) && v.has(e.kind) && y.has(e.taskType) && b.has(e.labelCode) && x.has(e.status) && Number.isInteger(e.progress) && e.progress >= 0 && e.progress <= 100 && x.has(e.messageCode) && typeof e.createdAt == "string" && j.test(e.createdAt) && typeof e.updatedAt == "string" && j.test(e.updatedAt) && n(e.startedAt) && n(e.finishedAt) && t(e.errorCode, O) && S.has(e.generationMode) && C.has(e.adapter) && t(e.requestedMode, w) && T.has(e.mode) && t(e.attemptedEngine, E) && t(e.finalEngine, E) && t(e.fallbackReason, D) && Array.isArray(e.artifactTypes) && e.artifactTypes.every((e) => typeof e == "string") && Number.isInteger(e.artifactCount) && e.artifactCount >= 0 && (e.proposalId === null || typeof e.proposalId == "string") && t(e.proposalStatus, k) && t(e.resultStatus, A);
}
function P(e) {
	if (!M(e, h) || e.schemaVersion !== 1 || !Number.isInteger(e.storeRevision) || !Number.isInteger(e.jobsStoreRevision) || !Number.isInteger(e.total) || !Array.isArray(e.entries) || !e.entries.every(N) || !M(e.retention, g) || e.retention.maxEntries !== 200 || e.retention.maxDays !== 30) throw Error("work_log_contract_invalid");
	return e;
}
var F = class extends Error {
	path;
	status;
	code;
	payload;
	name = "ApiRequestError";
	constructor(e, t, n, r) {
		super(`${e} failed: ${t}${n ? ` (${n})` : ""}`), this.path = e, this.status = t, this.code = n, this.payload = r;
	}
};
function I(e) {
	return e === "queued" || e === "running" || e === "cancel_requested" || e === "committing";
}
function L(e) {
	return typeof e == "object" && !!e && !Array.isArray(e);
}
async function R(e) {
	try {
		return await e.json();
	} catch {
		return null;
	}
}
async function z(e, t) {
	let n = await fetch(e, t), r = await R(n);
	if (!n.ok) {
		let t = L(r) ? r : null, i = t?.error, a = typeof i == "string" ? i : "request_failed";
		throw new F(e, n.status, a, t);
	}
	if (r === null) throw Error(`${e} returned an empty response`);
	return r;
}
async function B(e, t = {}) {
	return z(e, {
		headers: { "Content-Type": "application/json" },
		signal: t.signal
	});
}
async function V(e, t, n = {}) {
	return z(e, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(t),
		signal: n.signal
	});
}
async function H(e, t = {}) {
	return B(`/api/investment-notes/${encodeURIComponent(e)}/intelligence`, t);
}
async function U(e, t, n = {}) {
	return V(`/api/theses/${encodeURIComponent(e)}/review/checkpoints`, t, n);
}
async function ee(e, t = {}) {
	return V(`/api/theses/${encodeURIComponent(e)}/delta`, { period: "90d" }, t);
}
async function te(e, t, n = {}) {
	return z(e, {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(t),
		signal: n.signal
	});
}
async function W(e, t, n = {}) {
	return z(e, {
		method: "DELETE",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(t),
		signal: n.signal
	});
}
//#endregion
//#region node_modules/react/cjs/react-jsx-runtime.production.js
var G = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.fragment");
	function r(e, n, r) {
		var i = null;
		if (r !== void 0 && (i = "" + r), n.key !== void 0 && (i = "" + n.key), "key" in n) for (var a in r = {}, n) a !== "key" && (r[a] = n[a]);
		else r = n;
		return n = r.ref, {
			$$typeof: t,
			type: e,
			key: i,
			ref: n === void 0 ? null : n,
			props: r
		};
	}
	e.Fragment = n, e.jsx = r, e.jsxs = r;
})), K = (/* @__PURE__ */ e(((e, t) => {
	t.exports = G();
})))();
function q({ workspace: e }) {
	let t = (0, l.useRef)(null), [n, r] = (0, l.useState)(!1);
	return /* @__PURE__ */ (0, K.jsxs)("form", {
		className: "agent-home-prompt",
		onSubmit: e.handleSubmit,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "agent-home-prompt-shell",
				children: [/* @__PURE__ */ (0, K.jsx)("textarea", {
					value: e.input,
					onChange: (t) => e.setInput(t.target.value),
					onKeyDown: (e) => {
						e.key === "Enter" && !e.shiftKey && (e.preventDefault(), e.currentTarget.form?.requestSubmit());
					},
					placeholder: "오늘 어떤 투자 리서치를 도와드릴까요?",
					rows: 3
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "agent-home-toolbar",
					children: [
						/* @__PURE__ */ (0, K.jsx)("input", {
							ref: t,
							type: "file",
							multiple: !0,
							hidden: !0,
							onChange: (n) => {
								e.handleFiles(n.currentTarget.files).finally(() => {
									t.current && (t.current.value = "");
								});
							}
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "agent-home-toolbar-left",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								className: "btn btn--icon agent-home-icon-btn",
								onClick: () => t.current?.click(),
								"aria-label": "파일 첨부",
								"data-tooltip": "파일 첨부",
								children: "+"
							}), /* @__PURE__ */ (0, K.jsx)("span", {
								className: "agent-home-provider",
								children: e.adapter?.label || e.adapter?.id || "Folio OS"
							})]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "agent-home-toolbar-right",
							children: [
								/* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									className: "agent-home-icon-btn agent-home-advanced-toggle",
									"aria-expanded": n,
									onClick: () => r((e) => !e),
									children: "상세 설정"
								}),
								n && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("select", {
									"aria-label": "모델",
									value: e.model,
									onChange: (t) => e.persistModel(t.target.value),
									children: e.modelChoices.length > 0 ? e.modelChoices.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
										value: e.value,
										children: e.label
									}, e.value)) : /* @__PURE__ */ (0, K.jsx)("option", {
										value: "",
										children: "모델 목록 없음"
									})
								}), /* @__PURE__ */ (0, K.jsxs)("select", {
									"aria-label": "노력 단계",
									value: e.effort,
									onChange: (t) => e.setEffort(t.target.value),
									children: [
										/* @__PURE__ */ (0, K.jsx)("option", {
											value: "low",
											children: "낮음"
										}),
										/* @__PURE__ */ (0, K.jsx)("option", {
											value: "medium",
											children: "중간"
										}),
										/* @__PURE__ */ (0, K.jsx)("option", {
											value: "high",
											children: "높음"
										}),
										/* @__PURE__ */ (0, K.jsx)("option", {
											value: "max",
											children: "최대"
										})
									]
								})] }),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn btn--icon btn--primary agent-home-send",
									type: "submit",
									disabled: e.busy || !e.input.trim(),
									"aria-label": "전송",
									"data-tooltip": "전송",
									children: e.busy ? "..." : "↑"
								})
							]
						})
					]
				})]
			}),
			e.settingsMessage && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "agent-home-notice",
				children: e.settingsMessage
			}),
			e.attachments.length > 0 && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "agent-home-attachments",
				children: e.attachments.map((t) => /* @__PURE__ */ (0, K.jsxs)("span", { children: [
					t.name,
					t.imageData ? /* @__PURE__ */ (0, K.jsx)("em", {
						className: "agent-attachment-note",
						children: "이미지 · Agent가 직접 읽음"
					}) : null,
					!t.imageData && !t.content ? /* @__PURE__ */ (0, K.jsx)("em", {
						className: "agent-attachment-note",
						children: "본문 미포함"
					}) : null,
					/* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "btn btn--icon",
						"aria-label": `${t.name} 첨부 제거`,
						onClick: () => e.setAttachments((e) => e.filter((e) => e.name !== t.name)),
						children: "×"
					})
				] }, t.name))
			}),
			e.quickStatus && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "agent-home-notice",
				children: e.quickStatus
			}),
			e.error && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "agent-home-error",
				children: e.error
			})
		]
	});
}
//#endregion
//#region src/app/AgentMessageContent.tsx
function ne(e) {
	let t = [], n = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g, r = 0;
	for (let i of e.matchAll(n)) i.index !== void 0 && (i.index > r && t.push({
		type: "text",
		value: e.slice(r, i.index)
	}), i[2] ? t.push({
		type: "strong",
		value: i[2]
	}) : i[3] ? t.push({
		type: "code",
		value: i[3]
	}) : i[4] && i[5] && t.push({
		type: "link",
		label: i[4],
		href: i[5]
	}), r = i.index + i[0].length);
	return r < e.length && t.push({
		type: "text",
		value: e.slice(r)
	}), t;
}
function re(e) {
	return ne(e).map((e, t) => e.type === "strong" ? /* @__PURE__ */ (0, K.jsx)("strong", { children: e.value }, t) : e.type === "code" ? /* @__PURE__ */ (0, K.jsx)("code", { children: e.value }, t) : e.type === "link" ? /^https?:\/\//i.test(e.href) ? /* @__PURE__ */ (0, K.jsx)("a", {
		href: e.href,
		target: "_blank",
		rel: "noreferrer",
		children: e.label
	}, t) : /* @__PURE__ */ (0, K.jsx)("code", {
		title: e.href,
		children: e.label
	}, t) : /* @__PURE__ */ (0, K.jsx)("span", { children: e.value }, t));
}
function ie(e, t) {
	e.length &&= (t.push(/* @__PURE__ */ (0, K.jsx)("p", { children: re(e.join(" ")) }, `p-${t.length}`)), 0);
}
function ae({ text: e = "" }) {
	let t = [], n = [], r = [], i = "";
	function a() {
		if (!r.length) return;
		let e = r.map((e, t) => /* @__PURE__ */ (0, K.jsx)("li", { children: re(e) }, t));
		t.push(i === "ol" ? /* @__PURE__ */ (0, K.jsx)("ol", { children: e }, `ol-${t.length}`) : /* @__PURE__ */ (0, K.jsx)("ul", { children: e }, `ul-${t.length}`)), r = [], i = "";
	}
	for (let o of e.replace(/\r\n/g, "\n").split("\n")) {
		let e = o.trim();
		if (!e) {
			ie(n, t), a();
			continue;
		}
		let s = e.match(/^(#{2,4})\s+(.+)$/);
		if (s) {
			ie(n, t), a(), t.push(/* @__PURE__ */ (0, K.jsx)("h4", { children: re(s[2]) }, `h-${t.length}`));
			continue;
		}
		let c = e.match(/^\d+[.)]\s+(.+)$/);
		if (c) {
			ie(n, t), i && i !== "ol" && a(), i = "ol", r.push(c[1]);
			continue;
		}
		let l = e.match(/^[-*•]\s+(.+)$/);
		if (l) {
			ie(n, t), i && i !== "ul" && a(), i = "ul", r.push(l[1]);
			continue;
		}
		if (r.length) {
			r[r.length - 1] = `${r[r.length - 1]} ${e}`;
			continue;
		}
		n.push(e);
	}
	return ie(n, t), a(), /* @__PURE__ */ (0, K.jsx)("div", {
		className: "agent-chat-markdown",
		children: t
	});
}
function oe({ state: e = "pending", title: t, meta: n }) {
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: `agent-run-card ${e}`,
		children: [/* @__PURE__ */ (0, K.jsx)("span", {
			className: "agent-run-icon",
			"aria-hidden": "true"
		}), /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsxs)("strong", { children: [t, e === "pending" && /* @__PURE__ */ (0, K.jsx)("span", {
			className: "agent-run-eta",
			children: "보통 40~60초"
		})] }), n && /* @__PURE__ */ (0, K.jsx)("span", { children: n })] })]
	});
}
//#endregion
//#region src/app/agentProposalLifecycle.ts
var se = "folio:proposal-lifecycle", ce = 1e3, le = 12e3, ue = "수정 제안을 불러오지 못했습니다. Agent 작업 기록에서 다시 확인해 주세요.", de = /* @__PURE__ */ new Set([
	"applied",
	"rejected",
	"stale",
	"conflict",
	"failed_apply"
]), fe = /* @__PURE__ */ new Set([
	"pending",
	"applying",
	...de
]), pe = /* @__PURE__ */ new Set([
	"briefing",
	"company_analysis",
	"topic_report"
]), me = /* @__PURE__ */ new Set([
	"both",
	"us",
	"kr",
	"none"
]), he = [
	"marketScope",
	"proposalId",
	"reportId",
	"reportKind",
	"status",
	"targetRevision"
].sort(), ge = ["hash", "number"].sort(), _e = /^[0-9a-f]{64}$/, ve = /^(?:[0-9a-f]{12}|[0-9a-f]{32})$/, ye = {
	proposal: null,
	proposalStatus: "",
	notice: ""
};
function be(e) {
	return String(e || "").slice(0, ce);
}
function xe(e) {
	return String(e || "").slice(0, le);
}
function Se() {
	throw Error("proposal_contract_invalid");
}
function Ce(e) {
	return typeof e == "object" && !!e && !Array.isArray(e);
}
function we(e, t) {
	if (!Ce(e)) return !1;
	let n = Object.keys(e).sort();
	return n.length === t.length && n.every((e, n) => e === t[n]);
}
function Te(e) {
	return typeof e == "string" && e.trim().length > 0;
}
function Ee(e) {
	return typeof e == "string" && fe.has(e);
}
function De(e) {
	return typeof e == "string" && pe.has(e);
}
function Oe(e) {
	return typeof e == "string" && me.has(e);
}
function ke() {
	return {
		proposal: null,
		proposalStatus: "",
		notice: ue
	};
}
function Ae(e, t) {
	return (!Ce(e) || e.schemaVersion !== 2 || e.id !== t || !ve.test(t) || e.status !== "pending" && e.status !== "applying" || !De(e.reportKind) || !Te(e.reportId) || !Oe(e.marketScope) || typeof e.summary != "string" || typeof e.diff != "string") && Se(), {
		proposal: {
			id: t,
			summary: e.summary,
			diff: e.diff,
			artifactKind: e.reportKind,
			artifactId: e.reportId,
			marketScope: e.marketScope
		},
		proposalStatus: e.status,
		notice: ""
	};
}
async function je(e, t = { get: (e) => B(e) }) {
	if (!Ce(e) || !("proposalId" in e) || e.proposalId === null || e.proposalId === "") return ye;
	if (typeof e.proposalId != "string" || !ve.test(e.proposalId)) return ke();
	let n = e.proposalId;
	try {
		return Ae(await t.get(`/api/agent/proposals/${encodeURIComponent(n)}`), n);
	} catch {
		return ke();
	}
}
function Me(e) {
	return e === null ? null : ((!we(e, ge) || typeof e.number != "number" || !Number.isInteger(e.number) || e.number < 1 || typeof e.hash != "string" || !_e.test(e.hash)) && Se(), {
		number: e.number,
		hash: e.hash
	});
}
function Ne(e, t) {
	(!Ce(e) || !Ee(e.status) || !De(e.reportKind) || !Oe(e.marketScope)) && Se();
	let n = Te(e.proposalId) ? e.proposalId : t && Te(e.id) ? e.id : Se();
	return Te(e.reportId) || Se(), {
		proposalId: n,
		status: e.status,
		reportKind: e.reportKind,
		reportId: e.reportId,
		marketScope: e.marketScope,
		targetRevision: Me(e.targetRevision)
	};
}
function Pe(e, t) {
	we(e, he) || Se();
	let n = Ne(e, !1), r = t === "approve" ? "applied" : t === "reject" ? "rejected" : Se();
	return n.status !== r && Se(), n;
}
async function Fe(e, t, n) {
	(!Te(e) || t !== "approve" && t !== "reject") && Se();
	let r = `/api/agent/proposals/${encodeURIComponent(e)}`;
	try {
		return Pe(await n.post(r, { action: t }), t);
	} catch (e) {
		if (!(e instanceof F) || e.status >= 200 && e.status < 300) throw e;
		let t;
		try {
			t = Ne(await n.get(r), !0);
		} catch {
			throw e;
		}
		if (!de.has(t.status)) throw e;
		return t;
	}
}
function Ie(e, t) {
	return Fe(e, t, {
		post: (e, t) => V(e, t),
		get: (e) => B(e)
	});
}
function Le(e) {
	window.dispatchEvent(new CustomEvent(se, { detail: e }));
}
function Re(e, t) {
	return e.status !== "applied" || !t || t.reportKind !== e.reportKind || String(t.reportId || "") !== e.reportId ? !1 : e.reportKind !== "briefing" || String(t.marketScope || "") === e.marketScope;
}
//#endregion
//#region src/app/agentWorkspace/AgentThread.tsx
function ze({ workspace: e }) {
	return e.hasConversation ? /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "agent-home-thread agent-home-right",
		"aria-label": "AI Agent 대화",
		children: [/* @__PURE__ */ (0, K.jsxs)("div", {
			className: "agent-home-section-head",
			children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
				className: "section-kicker",
				children: "Agent Thread"
			}), /* @__PURE__ */ (0, K.jsx)("h2", { children: "현재 대화" })] }), /* @__PURE__ */ (0, K.jsx)("button", {
				type: "button",
				onClick: e.startNewConversation,
				children: "새 대화"
			})]
		}), /* @__PURE__ */ (0, K.jsx)("div", {
			className: "agent-home-log",
			"aria-live": "polite",
			children: e.messages.map((t) => /* @__PURE__ */ (0, K.jsxs)("article", {
				className: `agent-home-message ${t.role}${t.pending ? " pending" : ""}`,
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "agent-home-message-body",
					children: [
						t.runTitle && /* @__PURE__ */ (0, K.jsx)(oe, {
							state: t.runState === "still-running" ? "pending" : t.runState,
							title: t.runTitle,
							meta: t.runMeta
						}),
						t.runState === "still-running" && t.jobId && /* @__PURE__ */ (0, K.jsx)("div", {
							"data-qa": "agent-job-still-running",
							children: /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"data-qa": "agent-job-resume",
								onClick: () => void e.resumeAgentJob(t.id, t.jobId),
								children: "상태 다시 확인"
							})
						}),
						t.text && /* @__PURE__ */ (0, K.jsx)(ae, { text: t.text }),
						t.notice && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "agent-home-notice",
							children: t.notice
						}),
						(t.attachments || []).length > 0 && /* @__PURE__ */ (0, K.jsx)("div", {
							className: "agent-home-attachments",
							children: t.attachments?.map((e) => /* @__PURE__ */ (0, K.jsx)("span", { children: e }, e))
						})
					]
				}), t.proposal && /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "agent-home-proposal",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "수정 제안" }), /* @__PURE__ */ (0, K.jsxs)("span", { children: [
							t.proposal.artifactKind,
							" ",
							t.proposal.artifactId
						] })] }),
						t.proposalStatus === "pending" && t.proposal.summary && /* @__PURE__ */ (0, K.jsx)("p", {
							"data-qa": "proposal-summary",
							children: be(t.proposal.summary)
						}),
						t.proposalStatus === "pending" && t.proposal.diff && /* @__PURE__ */ (0, K.jsxs)("details", { children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "diff 보기" }), /* @__PURE__ */ (0, K.jsx)("pre", {
							"data-qa": "proposal-diff",
							children: xe(t.proposal.diff)
						})] }),
						t.proposalStatus === "pending" ? /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "agent-home-proposal-actions",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"data-qa": "proposal-approve",
								onClick: () => e.handleProposalAction(t.id, t.proposal.id, "approve"),
								children: "승인"
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"data-qa": "proposal-reject",
								onClick: () => e.handleProposalAction(t.id, t.proposal.id, "reject"),
								children: "거절"
							})]
						}) : /* @__PURE__ */ (0, K.jsxs)("p", {
							className: "agent-home-notice",
							"data-qa": t.proposalStatus === "applied" ? "wb-happy-applied" : t.proposalStatus === "rejected" ? "wb-f1-terminal-rejected" : t.proposalStatus === "stale" ? "wb-f1-terminal-stale" : "proposal-terminal",
							children: ["상태: ", t.proposalStatus]
						})
					]
				})]
			}, t.id))
		})]
	}) : null;
}
//#endregion
//#region src/app/agentWorkspace/presenters.ts
var Be = /* @__PURE__ */ new Set([
	"codex",
	"claude",
	"antigravity"
]);
function Ve(e) {
	return e === "high" ? "높음" : e === "low" ? "낮음" : e === "max" ? "최대" : "중간";
}
function He(e) {
	return `${Math.max(1, Math.round((Date.now() - e) / 1e3))}초`;
}
function Ue(e) {
	let t = e?.provider && Be.has(e.provider) ? e.provider : e?.selectedAdapter || "";
	return e?.adapters?.find((e) => e.id === t) || null;
}
function We(e) {
	return e?.modelChoices || [];
}
function Ge(e) {
	let t = We(e);
	return t.length ? t.some((t) => t.value === e?.model) ? String(e?.model || "") : t[0].value : "";
}
function Ke(e) {
	let t = e;
	return !!(t?.id && ["queued", "running"].includes(t.status));
}
function qe(e) {
	let t = String(e.view || "").trim(), n = e.marketScope === "us" || e.marketScope === "kr" || e.marketScope === "both" ? e.marketScope : e.scope === "us" || e.scope === "kr" || e.scope === "both" ? e.scope : "both";
	return t === "briefing" && /^\d{4}-\d{2}-\d{2}$/.test(String(e.date || "")) ? `#/briefing/${e.date}/${n}` : `#/${{
		review: "dashboard",
		dashboard: "dashboard",
		briefing: "briefing",
		rssfeed: "rss",
		memory: "market-memory",
		analysis: "analysis",
		topicrpt: "deep-research",
		watchlist: "watchlist",
		settings: "settings"
	}[t] || "dashboard"}`;
}
function Je(e, t) {
	return `${e.view || "report"}-${e.date || ""}-${e.title || t}`;
}
//#endregion
//#region src/app/agentContext.ts
var Ye = /* @__PURE__ */ new Map(), Xe = "";
function Ze(e) {
	let t = { ...e };
	return window.FolioAgent = {
		...window.FolioAgent || {},
		currentContext: t
	}, t;
}
function Qe(e, t = {}) {
	let n = { ...t };
	return Ye.set(e, n), Xe === e ? Ze(n) : n;
}
function $e(e, t = {}) {
	return Qe(e, {
		...Ye.get(e) || {},
		...t
	});
}
function et(e) {
	Ye.delete(e), Xe === e && Ze({});
}
function tt(e, t = {}) {
	Xe = e, Ye.has(e) || Ye.set(e, { ...t });
	let n = { ...Ye.get(e) || {} };
	return delete n.selectedText, delete n.visibleSection, Ye.set(e, n), Ze(n);
}
function nt(e = {}) {
	Xe ? $e(Xe, e) : Ze(e), window.FolioBridge?.openAgentDock?.(e);
}
//#endregion
//#region src/app/agentPolling.ts
var rt = 1e3, it = 12e4, at = class extends Error {
	job;
	name = "AgentPollTimeout";
	constructor(e) {
		super("작업이 아직 실행 중입니다. 서버 작업은 계속되며 나중에 상태를 다시 확인할 수 있습니다."), this.job = e;
	}
}, ot = class extends Error {
	job;
	name = "AgentJobTerminalError";
	constructor(e) {
		super(e.message || e.error || `Agent 작업이 ${e.status} 상태로 종료되었습니다.`), this.job = e;
	}
};
function st(e, t, n) {
	let r = e.get(t);
	r !== n && r?.abort(), e.set(t, n);
}
function ct(e, t, n) {
	return e.get(t) === n && (e.delete(t), !0);
}
function lt(e, t) {
	return new Promise((n, r) => {
		if (t?.aborted) {
			r(new DOMException("Polling aborted", "AbortError"));
			return;
		}
		let i = window.setTimeout(() => {
			t?.removeEventListener("abort", a), n();
		}, e), a = () => {
			window.clearTimeout(i), r(new DOMException("Polling aborted", "AbortError"));
		};
		t?.addEventListener("abort", a, { once: !0 });
	});
}
async function ut(e, t = {}) {
	let { signal: n, timeoutMs: r = it, intervalMs: i = rt, onUpdate: a } = t, o = Date.now() + r, s = e;
	for (; I(s.status);) {
		if (Date.now() >= o) throw new at(s);
		await lt(i, n), s = await B(`/api/jobs/${encodeURIComponent(s.id)}`, { signal: n }), a?.(s);
	}
	if (s.status !== "done") throw new ot(s);
	return s;
}
function dt(e, t = {}) {
	return ut(e, {
		...t,
		timeoutMs: Infinity
	});
}
//#endregion
//#region src/app/agentWorkspace/storage.ts
var ft = "folio.agentHome.thread.v1", pt = {
	id: "welcome",
	role: "assistant",
	text: "무엇을 조사하거나 정리할까요? 질문으로 시작해도 되고, 보고서 수정 작업을 지시해도 됩니다.",
	notice: "저장 변경은 proposal 승인 전에는 반영되지 않습니다."
};
function mt(e) {
	return e.id === "welcome" || e.variant === "welcome";
}
function ht(e) {
	return e.filter((e) => !mt(e)).map((e) => ({
		...e,
		pending: !1,
		text: e.pending ? `${e.text}\n\n이전 세션에서 완료 여부를 확인하지 못했습니다.` : e.text
	})).slice(-80);
}
function gt() {
	if (typeof window > "u") return [pt];
	try {
		let e = window.localStorage.getItem(ft);
		if (!e) return [pt];
		let t = JSON.parse(e), n = Array.isArray(t?.messages) ? t.messages.filter((e) => e?.role === "user" || e?.role === "assistant") : [];
		return n.length ? [pt, ...n] : [pt];
	} catch {
		return [pt];
	}
}
var _t = gt(), vt = JSON.stringify(ht(_t)), yt = /* @__PURE__ */ new Set();
function bt() {
	let e = [..._t];
	yt.forEach((t) => t(e));
}
function xt() {
	return [..._t];
}
function St(e) {
	let t = ht(e), n = JSON.stringify(t);
	if (n !== vt) {
		if (_t = e.length ? [...e] : [pt], vt = n, typeof window < "u") try {
			t.length ? window.localStorage.setItem(ft, JSON.stringify({
				version: 1,
				updatedAt: (/* @__PURE__ */ new Date()).toISOString(),
				messages: t
			})) : window.localStorage.removeItem(ft);
		} catch {}
		bt();
	}
}
function Ct() {
	if (_t = [pt], vt = "[]", typeof window < "u") try {
		window.localStorage.removeItem(ft);
	} catch {}
	bt();
}
function wt(e) {
	return yt.add(e), () => {
		yt.delete(e);
	};
}
function Tt() {
	return typeof window > "u" ? !1 : !!window.localStorage.getItem("folio.agentHome.thread.v1") && !window.localStorage.getItem("folio.consultation.legacyNotice.v1");
}
typeof window < "u" && window.addEventListener("storage", (e) => {
	e.key === "folio.agentHome.thread.v1" && (_t = gt(), vt = JSON.stringify(ht(_t)), bt());
});
//#endregion
//#region src/app/agentWorkspace/useAgentWorkspace.ts
var Et = 3, Dt = 2e5, Ot = 4e3, kt = 12582912;
function At() {
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
async function jt(e) {
	return ut(e);
}
async function Mt(e) {
	let t = new Uint8Array(await e.arrayBuffer()), n = "";
	for (let e = 0; e < t.length; e += 32768) n += String.fromCharCode(...t.subarray(e, e + 32768));
	return btoa(n);
}
function Nt(e) {
	return e.type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(e.name);
}
async function Pt(e) {
	if (Nt(e)) return {
		name: e.name.slice(0, 120),
		size: e.size,
		content: "",
		imageData: e.size <= kt ? await Mt(e) : ""
	};
	let t = e.type.startsWith("text/") || /\.(md|txt|csv|json)$/i.test(e.name) ? await e.text() : "";
	return {
		name: e.name.slice(0, 120),
		size: e.size,
		content: t.slice(0, Ot)
	};
}
function Ft(e = "agent_home") {
	let [t, n] = (0, l.useState)(() => xt()), [r, i] = (0, l.useState)(""), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(null), [u, d] = (0, l.useState)(""), [f, p] = (0, l.useState)("medium"), [m, h] = (0, l.useState)([]), [g, _] = (0, l.useState)([]), [v, y] = (0, l.useState)(0), b = (0, l.useRef)(/* @__PURE__ */ new Map()), [x, S] = (0, l.useState)(""), [C, w] = (0, l.useState)(""), [T, E] = (0, l.useState)(!1), [D, O] = (0, l.useState)(""), k = Tt();
	(0, l.useEffect)(() => {
		let t = e === "agent_home" ? "home" : "office";
		return Qe(t, {
			surface: e,
			viewId: t
		}), () => et(t);
	}, [e]), (0, l.useEffect)(() => wt(n), []), (0, l.useEffect)(() => {
		St(t);
	}, [t]);
	let A = (0, l.useCallback)((e, t = !1) => {
		let n = Ue(e);
		c(e), d(e.message || ""), o((e) => {
			let r = Ge(n);
			return t && We(n).some((t) => t.value === e) ? e : r;
		});
	}, []), j = (0, l.useCallback)(async (e = !1) => {
		let t = await B(`/api/agent-bridge/settings${e ? "?refresh=true" : ""}`);
		A(t, !0);
	}, [A]);
	(0, l.useEffect)(() => {
		let e = !0;
		return B("/api/agent-bridge/settings").then((t) => {
			e && A(t);
		}).catch((t) => {
			e && d(t instanceof Error ? t.message : "Agent 설정을 불러오지 못했습니다.");
		}), () => {
			e = !1;
		};
	}, [A]), (0, l.useEffect)(() => {
		let e = (e) => {
			let t = e.detail;
			t ? A(t) : j().catch((e) => {
				d(e instanceof Error ? e.message : "Agent 설정을 불러오지 못했습니다.");
			});
		};
		return window.addEventListener("folio:agent-settings-updated", e), () => window.removeEventListener("folio:agent-settings-updated", e);
	}, [A, j]), (0, l.useEffect)(() => {
		let e = !0;
		return Promise.allSettled([B("/api/dashboard"), B("/api/investment-review")]).then((t) => {
			if (!e) return;
			let n = t[0].status === "fulfilled" ? t[0].value : null, r = [...(t[1].status === "fulfilled" ? t[1].value : null)?.recentReports || [], ...n?.briefings || []], i = /* @__PURE__ */ new Set();
			_(r.filter((e, t) => {
				let n = `${e.view || ""}:${e.date || ""}:${e.title || t}`;
				return !i.has(n) && (i.add(n), !0);
			}).slice(0, 3));
		}), () => {
			e = !1;
		};
	}, []);
	let M = (0, l.useCallback)(() => y((e) => e + 1), []);
	function N() {
		Ct(), n(xt()), i(""), h([]), O(""), w("");
	}
	async function P(t) {
		t.preventDefault();
		let o = r.trim();
		if (!o || T) return;
		let c = {
			id: At(),
			role: "user",
			text: o,
			attachments: m.map((e) => e.name),
			createdAt: (/* @__PURE__ */ new Date()).toISOString()
		}, l = At(), u = Date.now(), d = Ue(s), p = d?.label || "Agent", g = a || d?.model || "model";
		n((e) => [
			...e,
			c,
			{
				id: l,
				role: "assistant",
				text: "",
				pending: !0,
				runState: "pending",
				runTitle: `${p} 세션 시작`,
				runMeta: `${g} · ${Ve(f)} · on-request`,
				createdAt: new Date(u).toISOString()
			}
		]), i(""), O(""), E(!0);
		let _ = null;
		try {
			let t = await V("/api/agent/chat", {
				message: o,
				context: { surface: e },
				options: {
					model: a,
					effort: f,
					attachments: m
				}
			});
			_ = new AbortController(), st(b.current, l, _);
			let r = await ut(t, { signal: _.signal });
			ct(b.current, l, _);
			let i = r.result || {}, s = await je(i);
			M(), n((e) => e.map((e) => e.id === l ? {
				...e,
				text: i.reply || r.message || "Agent가 응답을 반환하지 않았습니다.",
				notice: [i.notice, s.notice].filter(Boolean).join(" "),
				pending: !1,
				proposal: s.proposal,
				proposalStatus: s.proposalStatus,
				runState: "done",
				runTitle: `${p} 응답`,
				runMeta: `${g} · ${Ve(f)} · ${He(u)}`
			} : e)), h([]);
		} catch (e) {
			if (_ && ct(b.current, l, _), e instanceof at) {
				n((t) => t.map((t) => t.id === l ? {
					...t,
					text: e.message,
					pending: !1,
					runState: "still-running",
					runTitle: `${p} 계속 실행 중`,
					runMeta: `${g} · ${Ve(f)} · ${He(u)}`,
					jobId: e.job.id
				} : t));
				return;
			}
			let t = e instanceof Error ? e.message : "Agent 요청에 실패했습니다.";
			O(t), n((e) => e.map((e) => e.id === l ? {
				...e,
				text: t,
				pending: !1,
				runState: "error",
				runTitle: `${p} 오류`,
				runMeta: `${g} · ${Ve(f)}`
			} : e));
		} finally {
			E(!1);
		}
	}
	async function F(e) {
		if (O(""), w(""), e === "analysis" || e === "deep-research") {
			window.location.hash = e === "analysis" ? "#/analysis" : "#/deep-research";
			return;
		}
		S(e);
		try {
			if (e === "rss") {
				w("RSS 수집을 시작했습니다.");
				let e = await V("/api/rssarchive/import", {});
				Ke(e) && await jt(e), M(), w("RSS 수집이 끝났습니다."), window.location.hash = "#/rss";
				return;
			}
			w("오늘 브리핑을 생성하는 중입니다.");
			let t = await V("/api/briefings", {
				marketScope: "both",
				briefingType: "default"
			}), n = "";
			if (Ke(t)) {
				let e = await jt(t);
				n = e.result?.date || e.result?.artifactId || "";
			} else n = t.date || "";
			M(), w(n ? "오늘 브리핑을 생성했습니다." : "브리핑 생성이 끝났습니다."), window.location.hash = n ? `#/briefing/${n}/both` : "#/briefing";
		} catch (e) {
			let t = e instanceof Error ? e.message : "빠른 실행에 실패했습니다.";
			O(t), w(t);
		} finally {
			S("");
		}
	}
	async function I(e) {
		if (!e) return;
		O("");
		let t = [...m];
		for (let n of Array.from(e)) {
			if (t.length >= Et) {
				O(`첨부는 최대 ${Et}개까지 가능합니다.`);
				break;
			}
			let e = Nt(n);
			if (n.size > (e ? kt : Dt)) {
				O(`${n.name}은 ${e ? "12MB" : "200KB"}를 초과해 제외했습니다.`);
				continue;
			}
			t.push(await Pt(n));
		}
		h(t);
	}
	async function L(e, t) {
		let r = new AbortController();
		st(b.current, e, r), n((t) => t.map((t) => t.id === e ? {
			...t,
			pending: !0,
			runState: "pending",
			runTitle: "Agent 상태 다시 확인 중"
		} : t));
		try {
			let i = await ut(await B(`/api/jobs/${encodeURIComponent(t)}`, { signal: r.signal }), { signal: r.signal }), a = i.result || {}, o = await je(a);
			M(), n((t) => t.map((t) => t.id === e ? {
				...t,
				text: a.reply || i.message || "Agent가 응답을 반환하지 않았습니다.",
				notice: [a.notice, o.notice].filter(Boolean).join(" "),
				proposal: o.proposal,
				proposalStatus: o.proposalStatus,
				pending: !1,
				runState: "done",
				runTitle: "Agent 응답",
				jobId: void 0
			} : t));
		} catch (t) {
			t instanceof at ? n((n) => n.map((n) => n.id === e ? {
				...n,
				text: t.message,
				pending: !1,
				runState: "still-running",
				runTitle: "Agent 계속 실행 중",
				jobId: t.job.id
			} : n)) : t instanceof DOMException && t.name === "AbortError" || n((n) => n.map((n) => n.id === e ? {
				...n,
				text: t instanceof Error ? t.message : "Agent 상태 확인에 실패했습니다.",
				pending: !1,
				runState: "error",
				runTitle: "Agent 오류"
			} : n));
		} finally {
			ct(b.current, e, r);
		}
	}
	async function R(e, t, r) {
		O("");
		try {
			let i = await Ie(t, r);
			n((t) => t.map((t) => t.id === e ? {
				...t,
				proposalStatus: i.status
			} : t)), Le(i), M();
		} catch (e) {
			O(e instanceof Error ? e.message : "제안 처리에 실패했습니다.");
		}
	}
	let z = Ue(s), H = We(z), U = t.some((e) => e.id !== "welcome");
	async function ee(e) {
		if (o(e), !(!z?.id || !e)) try {
			let t = Object.fromEntries((s?.adapters || []).map((e) => [e.id, e.model || ""]));
			t[z.id] = e;
			let n = await V("/api/agent-bridge/settings", {
				provider: z.id,
				models: t
			});
			A(n, !0), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: n }));
		} catch (e) {
			O(e instanceof Error ? e.message : "모델 설정 저장에 실패했습니다.");
		}
	}
	return {
		messages: t,
		input: r,
		setInput: i,
		model: a,
		effort: f,
		setEffort: p,
		attachments: m,
		setAttachments: h,
		recentReports: g || [],
		workLogRefreshKey: v,
		quickBusy: x,
		quickStatus: C,
		busy: T,
		error: D,
		settingsMessage: u,
		adapter: z,
		modelChoices: H,
		hasConversation: U,
		legacyConsultationImportAvailable: k,
		handleSubmit: P,
		handleFiles: I,
		handleProposalAction: R,
		resumeAgentJob: L,
		persistModel: ee,
		runQuickAction: F,
		startNewConversation: N
	};
}
//#endregion
//#region src/app/workLogCopy.ts
var It = {
	companion: "Agent와 대화",
	briefing: "일일 브리핑 생성",
	company_analysis: "기업 분석 생성",
	topic_report: "딥 리서치 생성",
	personal_overlay: "내 노트와 연결",
	thesis_delta: "투자 논거 변화 점검",
	market_memory_llm: "시장 메모리 정리",
	market_state_snapshot: "시장 상태 정리",
	market_memory_update: "시장 메모리 갱신",
	quality_repair: "보고서 품질 보완",
	investment_review: "투자 리뷰 생성",
	index: "자료 인덱스 갱신",
	rss: "RSS 수집",
	setup: "초기 설정"
}, Lt = {
	queued: "대기 중",
	running: "진행 중",
	committing: "저장 중",
	cancel_requested: "취소 요청됨",
	done: "완료",
	cancelled: "취소됨",
	failed: "실패",
	failed_cancel: "취소 중 실패",
	failed_commit: "저장 실패",
	failed_restart: "재시작 중 중단",
	failed_commit_recovery: "저장 복구 실패"
}, Rt = {
	queued: "waiting",
	running: "running",
	committing: "running",
	cancel_requested: "waiting",
	done: "done",
	cancelled: "cancelled"
}, zt = {
	llm_api: "AI 직접 호출",
	llm_cli: "AI CLI",
	rules: "규칙 기반",
	none: "실행 없음"
}, Bt = {
	auto: "자동 선택",
	codex: "Codex",
	claude: "Claude",
	antigravity: "Antigravity",
	openai_api: "OpenAI",
	gemini_api: "Gemini",
	claude_api: "Claude API",
	rules: "규칙 기반",
	none: "없음"
}, Vt = {
	briefing: "브리핑",
	company_analysis: "기업 분석",
	topic_report: "딥 리서치",
	personal_overlay: "개인 해석",
	market_state: "시장 상태",
	investment_review: "투자 리뷰",
	thesis_delta: "투자 논거 변화"
}, Ht = {
	engine_unavailable: "선택한 AI를 쓸 수 없어 다른 방법으로 실행했습니다.",
	engine_failed: "AI 실행이 실패해 다른 방법으로 대체했습니다.",
	confirmed_zero_evidence: "근거가 없는 상태를 확인하고 규칙 기반으로 실행했습니다."
}, Ut = {
	adapter_unavailable: "연결된 AI 도구를 찾지 못했습니다.",
	adapter_failed: "AI 도구 실행이 실패했습니다.",
	validation_failed: "요청 값이 올바르지 않아 중단했습니다.",
	save_failed: "결과를 저장하지 못했습니다.",
	cancel_failed: "취소 처리를 끝내지 못했습니다.",
	restart_interrupted: "서버 재시작으로 작업이 끊겼습니다.",
	commit_recovery_failed: "저장 복구에 실패했습니다.",
	private_cleanup_failed: "임시 파일 정리에 실패했습니다.",
	store_unavailable: "작업 저장소를 읽지 못했습니다.",
	internal_error: "예기치 못한 오류가 발생했습니다."
}, Wt = {
	pending: "승인 대기 중인 수정 제안이 있습니다.",
	applying: "수정 제안을 반영하는 중입니다.",
	applied: "수정 제안을 반영했습니다.",
	rejected: "수정 제안을 거절했습니다.",
	stale: "수정 제안이 만료되었습니다.",
	conflict: "수정 제안이 최신 보고서와 충돌합니다.",
	failed_apply: "수정 제안 반영에 실패했습니다.",
	unavailable: "수정 제안을 열 수 없습니다."
};
function Gt(e) {
	return e ? e.split("_").join(" ") : "";
}
function Kt(e) {
	return Rt[e.status] || (e.status.startsWith("failed") ? "failed" : "running");
}
function qt(e) {
	if (!e.artifactCount) return "";
	let t = e.artifactTypes.map((e) => Vt[e] || Gt(e)).filter(Boolean);
	return t.length ? `${t.join(", ")} ${e.artifactCount}건 저장` : `산출물 ${e.artifactCount}건 저장`;
}
function Jt(e) {
	let t = It[e.taskType] || Gt(e.taskType) || "Agent 작업", n = Lt[e.status] || Gt(e.status), r = Kt(e), i = qt(e), a = r === "running" || r === "waiting" ? e.progress > 0 ? `${e.progress}% 진행` : "시작을 기다리는 중" : r === "cancelled" ? "사용자가 중단했습니다." : r === "failed" ? Ut[e.errorCode || ""] || "작업을 끝내지 못했습니다." : i || (e.taskType === "companion" ? "답변을 마쳤습니다." : "저장한 산출물 없이 끝났습니다."), o = [], s = zt[e.generationMode], c = Bt[e.adapter];
	return s && e.generationMode !== "none" && o.push(c && e.adapter !== "none" ? `${s} · ${c}` : s), e.fallbackReason && o.push(Ht[e.fallbackReason] || Gt(e.fallbackReason)), r === "done" && i && a !== i && o.push(i), {
		title: t,
		statusLabel: n,
		tone: r,
		outcome: a,
		details: o,
		attention: e.proposalStatus ? Wt[e.proposalStatus] || Gt(e.proposalStatus) : ""
	};
}
function Yt(e, t) {
	if (t && !e) return "확인 중";
	if (!e) return "최근 작업 없음";
	let n = Jt(e);
	return `최근: ${n.title} · ${n.statusLabel}`;
}
//#endregion
//#region src/app/AgentWorkLog.tsx
function Xt(e) {
	return e instanceof F ? e.code || `http_${e.status}` : e instanceof Error && /^[a-z0-9_]+$/.test(e.message) ? e.message : "request_failed";
}
function Zt(e) {
	let t = new Date(e);
	return Number.isNaN(t.getTime()) ? "시간 확인 불가" : new Intl.DateTimeFormat("ko-KR", {
		dateStyle: "short",
		timeStyle: "short"
	}).format(t);
}
function Qt({ surface: e, pageSize: t = 20, defaultFilter: n = "all", refreshKey: r = 0, collapsible: i = !1 }) {
	let [a, o] = (0, l.useState)(n), [s, c] = (0, l.useState)(0), [u, d] = (0, l.useState)(null), [f, p] = (0, l.useState)(!0), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(null), [v, y] = (0, l.useState)(null), [b, x] = (0, l.useState)(!1), [S, C] = (0, l.useState)(""), [w, T] = (0, l.useState)(""), [E, D] = (0, l.useState)(null), [O, k] = (0, l.useState)(""), [A, j] = (0, l.useState)(""), M = (0, l.useRef)(0), N = (0, l.useRef)(null), F = (0, l.useRef)(!1), I = (0, l.useRef)(!1), L = (0, l.useRef)(null), R = (0, l.useRef)(null), z = (0, l.useCallback)(async () => {
		let e = ++M.current;
		N.current?.abort();
		let n = new AbortController();
		N.current = n, p(!0), h("");
		try {
			let r = P(await B(`/api/agent/work-log?kind=${a}&limit=${t}&offset=${s}`, { signal: n.signal }));
			if (e !== M.current) return;
			d(r);
		} catch (t) {
			if (n.signal.aborted || e !== M.current) return;
			h(Xt(t));
		} finally {
			e === M.current && p(!1);
		}
	}, [
		a,
		s,
		t
	]);
	(0, l.useEffect)(() => (z(), () => N.current?.abort()), [z, r]), (0, l.useEffect)(() => {
		let e = () => {
			D(null), z();
		};
		return window.addEventListener(se, e), () => window.removeEventListener(se, e);
	}, [z]), (0, l.useEffect)(() => {
		if (!g) return;
		L.current?.querySelector("button:not([disabled]), input:not([disabled])")?.focus();
		let e = (e) => {
			if (e.key === "Escape" && H(), e.key !== "Tab" || !L.current) return;
			let t = Array.from(L.current.querySelectorAll("button:not([disabled]), input:not([disabled])"));
			if (!t.length) return;
			let n = t[0], r = t[t.length - 1];
			e.shiftKey && document.activeElement === n ? (e.preventDefault(), r.focus()) : !e.shiftKey && document.activeElement === r && (e.preventDefault(), n.focus());
		};
		return document.addEventListener("keydown", e), () => document.removeEventListener("keydown", e);
	}, [g]);
	function H() {
		_(null), y(null), C(""), window.setTimeout(() => R.current?.focus(), 0);
	}
	function U(e) {
		o(e), c(0), D(null), j("");
	}
	async function ee(e) {
		if (!F.current) {
			F.current = !0, R.current = e, x(!0), C(""), T("");
			try {
				let e = await V("/api/agent/work-log/clear-preview", { scope: a });
				y(e), _("clear");
			} catch (e) {
				C(Xt(e));
			} finally {
				F.current = !1, x(!1);
			}
		}
	}
	async function te() {
		if (!(!v || F.current)) {
			F.current = !0, x(!0), C("");
			try {
				let e = await W("/api/agent/work-log", {
					scope: v.scope,
					previewToken: v.previewToken
				});
				T(`${e.hiddenCount}건을 목록에서 숨겼습니다.`), H(), c(0), await z();
			} catch (e) {
				y(null), C(Xt(e));
			} finally {
				F.current = !1, x(!1);
			}
		}
	}
	async function G(e) {
		if (!(!e.proposalId || I.current)) {
			I.current = !0, k(e.proposalId), j(""), D(null);
			try {
				let t = await B(`/api/agent/proposals/${encodeURIComponent(e.proposalId)}`);
				if (t.id !== e.proposalId) throw Error("proposal_identity_mismatch");
				if (t.status !== "pending" && t.status !== "applying") throw Error("proposal_not_active");
				D(t);
			} catch (e) {
				j(Xt(e)), await z();
			} finally {
				I.current = !1, k("");
			}
		}
	}
	let q = u?.entries || [], ne = !!(u && s + t < u.total), re = Yt(q[0], f && !u), ie = a !== "all" || (u?.total ?? 0) > 1, ae = !!(u && u.total > t), oe = /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
		!i && /* @__PURE__ */ (0, K.jsx)("header", {
			className: "work-log-head",
			children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
				className: "section-kicker",
				children: "Agent Work Log"
			}), /* @__PURE__ */ (0, K.jsx)("h2", { children: "Agent 작업 기록" })] })
		}),
		/* @__PURE__ */ (0, K.jsxs)("div", {
			className: "work-log-toolbar",
			children: [ie ? /* @__PURE__ */ (0, K.jsx)("div", {
				className: "work-log-filters",
				"data-qa": "work-log-filter",
				"aria-label": "작업 범주",
				children: [
					"all",
					"companion",
					"task"
				].map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "btn",
					"data-qa": `work-log-filter-${e}`,
					"aria-pressed": a === e,
					onClick: () => U(e),
					children: e === "all" ? "전체" : e === "companion" ? "대화" : "작업"
				}, e))
			}) : /* @__PURE__ */ (0, K.jsx)("span", {}), /* @__PURE__ */ (0, K.jsx)("button", {
				className: "btn btn--icon",
				type: "button",
				"data-qa": "work-log-refresh",
				disabled: f,
				onClick: () => void z(),
				"aria-label": "작업 기록 새로고침",
				"data-tooltip": "새로고침",
				children: /* @__PURE__ */ (0, K.jsxs)("svg", {
					width: "15",
					height: "15",
					viewBox: "0 0 16 16",
					fill: "none",
					stroke: "currentColor",
					strokeWidth: "1.5",
					strokeLinecap: "round",
					strokeLinejoin: "round",
					"aria-hidden": "true",
					children: [/* @__PURE__ */ (0, K.jsx)("path", { d: "M13.5 8a5.5 5.5 0 1 1-1.6-3.9" }), /* @__PURE__ */ (0, K.jsx)("path", { d: "M13.5 2.5V6H10" })]
				})
			})]
		}),
		f && !u && /* @__PURE__ */ (0, K.jsx)("p", {
			"data-qa": "work-log-loading",
			role: "status",
			children: "작업 기록을 불러오는 중입니다."
		}),
		m && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "react-dashboard-error",
			"data-qa": "work-log-error",
			"data-error-code": m,
			role: "alert",
			children: [
				"작업 기록을 불러오지 못했습니다. (",
				m,
				")"
			]
		}),
		S && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "react-dashboard-error",
			"data-qa": "work-log-clear-error",
			"data-error-code": S,
			children: [
				"숨기기 미리보기가 만료되었거나 실패했습니다. 다시 미리보세요. (",
				S,
				")"
			]
		}),
		w && /* @__PURE__ */ (0, K.jsx)("p", {
			className: "react-dashboard-warning",
			"data-qa": "work-log-clear-success",
			role: "status",
			children: w
		}),
		A && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "react-dashboard-error",
			"data-qa": "work-log-proposal-error",
			"data-error-code": A,
			children: [
				"제안이 만료되었거나 현재 열 수 없습니다. (",
				A,
				")"
			]
		}),
		!f && !m && q.length === 0 && /* @__PURE__ */ (0, K.jsx)("p", {
			className: "work-log-empty",
			"data-qa": "work-log-empty",
			children: "표시할 Agent 작업 기록이 없습니다."
		}),
		q.length > 0 && /* @__PURE__ */ (0, K.jsx)("div", {
			className: "work-log-list",
			"data-qa": "work-log-list",
			children: q.map((e) => {
				let t = Jt(e);
				return /* @__PURE__ */ (0, K.jsxs)("article", {
					className: `work-log-item status-${e.status} tone-${t.tone}`,
					"data-qa": "work-log-item",
					"data-tone": t.tone,
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "work-log-item-main",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "work-log-item-title",
								children: [/* @__PURE__ */ (0, K.jsx)("strong", {
									"data-qa": "work-log-task-type",
									children: t.title
								}), /* @__PURE__ */ (0, K.jsx)("span", {
									className: "work-log-badge",
									"data-qa": "work-log-status",
									"data-tone": t.tone,
									children: t.statusLabel
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "work-log-outcome",
								"data-qa": "work-log-outcome",
								children: t.outcome
							}),
							t.details.length > 0 && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "work-log-detail",
								"data-qa": "work-log-execution",
								children: t.details.join(" · ")
							}),
							t.attention && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "work-log-attention",
								"data-qa": "work-log-proposal-status",
								children: t.attention
							})
						]
					}), /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "work-log-item-side",
						children: [/* @__PURE__ */ (0, K.jsx)("time", {
							"data-qa": "work-log-time",
							dateTime: e.updatedAt,
							children: Zt(e.finishedAt || e.updatedAt)
						}), e.proposalId && (e.proposalStatus === "pending" || e.proposalStatus === "applying") && /* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							className: "btn",
							"data-qa": "work-log-proposal-open",
							disabled: O === e.proposalId,
							onClick: () => void G(e),
							children: O === e.proposalId ? /* @__PURE__ */ (0, K.jsx)("span", {
								"data-qa": "work-log-proposal-loading",
								children: "불러오는 중"
							}) : "승인 검토"
						})]
					})]
				}, e.id);
			})
		}),
		u && /* @__PURE__ */ (0, K.jsxs)("footer", {
			className: "work-log-footer",
			children: [/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "work-log-footer-note",
				children: [/* @__PURE__ */ (0, K.jsxs)("p", {
					"data-qa": "work-log-retention",
					children: [
						"최근 ",
						u.retention.maxDays,
						"일, 최대 ",
						u.retention.maxEntries,
						"건을 표시합니다."
					]
				}), /* @__PURE__ */ (0, K.jsx)("p", { children: "작업 내용 원문이나 개인 자료 없이 진행 상태 요약만 표시합니다." })]
			}), /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "work-log-footer-actions",
				children: [ae && /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "work-log-pagination",
					children: [
						/* @__PURE__ */ (0, K.jsx)("span", {
							"data-qa": "work-log-page-summary",
							children: u.total ? `${s + 1}–${Math.min(s + t, u.total)} / ${u.total}` : "0 / 0"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"data-qa": "work-log-page-prev",
							disabled: s === 0 || f,
							onClick: () => c(Math.max(0, s - t)),
							children: "이전"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"data-qa": "work-log-page-next",
							disabled: !ne || f,
							onClick: () => c(s + t),
							children: "다음"
						})
					]
				}), q.length > 0 && /* @__PURE__ */ (0, K.jsx)("button", {
					className: "work-log-quiet-btn",
					type: "button",
					"data-qa": "work-log-clear-preview",
					disabled: b,
					onClick: (e) => void ee(e.currentTarget),
					children: "기록 숨기기"
				})]
			})]
		}),
		g === "clear" && v && /* @__PURE__ */ (0, K.jsx)("div", {
			className: "work-log-dialog-backdrop",
			children: /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "work-log-dialog",
				ref: L,
				role: "dialog",
				"aria-modal": "true",
				"aria-labelledby": "work-log-clear-title",
				"data-qa": "work-log-clear-dialog",
				children: [
					/* @__PURE__ */ (0, K.jsx)("h3", {
						id: "work-log-clear-title",
						children: "작업 기록 숨기기"
					}),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						"data-qa": "work-log-clear-count",
						children: [
							"현재 범위 ",
							v.count,
							"건"
						]
					}),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "목록에서만 숨깁니다. 공유 작업, 보고서, 제안, 레거시 파일은 삭제하지 않습니다." }),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "work-log-dialog-actions",
						children: [/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"data-qa": "work-log-clear-confirm",
							disabled: b,
							onClick: () => void te(),
							children: "숨기기 확인"
						}), /* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"data-qa": "work-log-clear-cancel",
							onClick: H,
							children: "취소"
						})]
					})
				]
			})
		}),
		E && /* @__PURE__ */ (0, K.jsxs)("aside", {
			className: "work-log-proposal-surface",
			"data-qa": "proposal-approval-surface",
			"aria-label": "활성 제안 승인 검토",
			children: [
				/* @__PURE__ */ (0, K.jsxs)("div", { children: [
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "승인 필요"
					}),
					/* @__PURE__ */ (0, K.jsx)("h3", { children: be(E.summary) || "저장 변경 제안" }),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "이 내용은 작업 기록이 아니라 요청 시 별도로 불러온 승인 제안입니다." })
				] }),
				E.diff && /* @__PURE__ */ (0, K.jsx)("pre", { children: xe(E.diff) }),
				/* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "btn",
					onClick: () => D(null),
					children: "닫기"
				})
			]
		})
	] });
	return /* @__PURE__ */ (0, K.jsx)("section", {
		className: `work-log work-log-${e}${i ? " work-log-collapsible" : ""}`,
		"data-qa": "work-log",
		"aria-busy": f,
		children: i ? /* @__PURE__ */ (0, K.jsxs)("details", {
			className: "work-log-collapse",
			children: [/* @__PURE__ */ (0, K.jsxs)("summary", { children: [
				/* @__PURE__ */ (0, K.jsx)("span", {
					className: "section-kicker",
					children: "Agent Work Log"
				}),
				/* @__PURE__ */ (0, K.jsx)("strong", { children: "Agent 작업 기록" }),
				/* @__PURE__ */ (0, K.jsx)("span", {
					className: "work-log-latest",
					"data-qa": "work-log-latest",
					children: re
				})
			] }), oe]
		}) : oe
	});
}
//#endregion
//#region src/app/FolioWordmark.tsx
function $t({ variant: e = "chrome" }) {
	return /* @__PURE__ */ (0, K.jsxs)("span", {
		className: "folio-wordmark",
		"data-variant": e,
		children: [
			/* @__PURE__ */ (0, K.jsx)("span", {
				className: "sr-only",
				children: "Folio OS"
			}),
			/* @__PURE__ */ (0, K.jsx)("span", {
				className: "folio-wordmark__word",
				"aria-hidden": "true",
				children: "folio"
			}),
			/* @__PURE__ */ (0, K.jsx)("span", {
				className: "folio-wordmark__bar",
				"aria-hidden": "true"
			}),
			/* @__PURE__ */ (0, K.jsx)("span", {
				className: "folio-wordmark__word",
				"aria-hidden": "true",
				children: "os"
			})
		]
	});
}
//#endregion
//#region src/app/InvestmentContextCard.tsx
var en = "folio.investmentContext.dismissed.v1", tn = {
	layer: "hypothesis",
	reuseAsEvidence: !1
}, nn = {
	home: {
		title: "내 리서치 연결",
		description: "관심 종목과 확인 일정을 현재 리서치 화면에만 연결합니다."
	},
	"market-memory": {
		title: "이 흐름과 연결된 종목",
		description: "시장 드라이버가 개인 포트폴리오·워치리스트와 만나는 지점입니다."
	},
	collection: {
		title: "이 Collection과 연결된 개인 맥락",
		description: "저장 필터와 겹치는 종목만 표시하며 외부 근거에는 포함하지 않습니다."
	},
	"deep-research": {
		title: "질문에 참고할 개인 맥락",
		description: "선택한 종목만 추가 컨텍스트에 hypothesis로 복사할 수 있습니다."
	}
};
function rn(e) {
	return e === "both" ? "포트폴리오 · 워치리스트" : e === "portfolio" ? "포트폴리오" : "워치리스트";
}
function an(e, t, n) {
	return t === "collection" ? e.watchContexts.filter((e) => e.collections.some((e) => e.id === n)) : e.watchContexts;
}
function on(e) {
	let t = e.marketDrivers.map((e) => e.label).slice(0, 2);
	return [
		rn(e.source),
		...t,
		e.dueCheckpoints.length ? `확인 예정 ${e.dueCheckpoints.length}` : ""
	].filter(Boolean).join(" · ");
}
function sn({ reply: e }) {
	let t = e.split(/\r?\n/).map((e) => e.trim()).filter(Boolean);
	return /* @__PURE__ */ (0, K.jsx)("div", {
		className: "investment-context-explanation-body",
		children: t.map((e, t) => e.startsWith("### ") ? /* @__PURE__ */ (0, K.jsx)("h3", { children: e.slice(4) }, `${t}:${e}`) : e.startsWith("- ") ? /* @__PURE__ */ (0, K.jsx)("p", {
			className: "is-bullet",
			children: e.slice(2)
		}, `${t}:${e}`) : /* @__PURE__ */ (0, K.jsx)("p", { children: e }, `${t}:${e}`))
	});
}
function cn({ mode: e, summary: t, collectionId: n, dismissible: r = !1, onDismiss: i, onReference: a, onExplain: o, explainingTicker: s = "", explanation: c = null, explanationError: u = "" }) {
	let d = (0, l.useMemo)(() => t ? an(t, e, n).slice(0, e === "home" ? 4 : 3) : [], [
		n,
		e,
		t
	]), f = nn[e];
	if (!t || !d.length) return null;
	let p = d.reduce((e, t) => e + t.dueCheckpoints.length, 0);
	return /* @__PURE__ */ (0, K.jsxs)("aside", {
		className: `investment-context-card mode-${e}`,
		"data-qa": `investment-context-${e}`,
		"data-layer": tn.layer,
		"data-reuse-as-evidence": String(tn.reuseAsEvidence),
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "investment-context-head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [
					/* @__PURE__ */ (0, K.jsx)("p", { children: "내 투자 맥락 · 가설 (근거 아님)" }),
					/* @__PURE__ */ (0, K.jsx)("h2", { children: f.title }),
					/* @__PURE__ */ (0, K.jsx)("span", { children: f.description })
				] }), r && i ? /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "btn btn--icon investment-context-dismiss",
					"aria-label": "개인 맥락 카드 닫기",
					onClick: i,
					children: "×"
				}) : null]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "investment-context-summary",
				"aria-label": "개인 맥락 요약",
				children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: ["연결 ", d.length] }), /* @__PURE__ */ (0, K.jsxs)("span", { children: ["확인 예정 ", p] })]
			}),
			/* @__PURE__ */ (0, K.jsx)("ul", {
				className: "investment-context-ledger",
				children: d.map((t) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: t.ticker }), /* @__PURE__ */ (0, K.jsx)("small", { children: on(t) })] }), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "investment-context-row-actions",
					children: [e === "deep-research" && a ? /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						onClick: () => a(t),
						children: "질문에 참고"
					}) : /* @__PURE__ */ (0, K.jsx)("a", {
						href: t.source === "watchlist" || t.source === "both" ? "#/watchlist" : "#/market-memory",
						children: "연결 보기"
					}), o ? /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						disabled: !!s,
						title: s && s !== t.ticker ? "다른 종목 설명이 끝나면 누를 수 있어요" : void 0,
						onClick: () => o(t),
						children: s === t.ticker ? "설명 중…" : "Agent로 위험 설명"
					}) : null]
				})] }, t.ticker))
			}),
			c ? /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "investment-context-explanation",
				"aria-live": "polite",
				children: [/* @__PURE__ */ (0, K.jsxs)("strong", { children: [c.ticker, " · Agent 설명"] }), /* @__PURE__ */ (0, K.jsx)(sn, { reply: c.reply })]
			}) : null,
			u ? /* @__PURE__ */ (0, K.jsx)("p", {
				className: "investment-context-error",
				role: "status",
				children: u
			}) : null,
			e === "home" ? /* @__PURE__ */ (0, K.jsxs)("nav", {
				className: "investment-context-links",
				"aria-label": "연결된 리서치 화면",
				children: [/* @__PURE__ */ (0, K.jsx)("a", {
					href: "#/market-memory",
					children: "시장 내러티브"
				}), /* @__PURE__ */ (0, K.jsx)("a", {
					href: "#/deep-research",
					children: "딥 리서치"
				})]
			}) : null,
			/* @__PURE__ */ (0, K.jsx)("small", {
				className: "investment-context-boundary",
				children: "개인 가설 레이어 · 외부 evidence 및 Canonical 본문과 분리"
			})
		]
	});
}
function ln(e) {
	let [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)(() => {
		try {
			return window.localStorage.getItem(en) === "1";
		} catch {
			return !1;
		}
	}), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(null), [u, d] = (0, l.useState)(""), f = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		let e = new AbortController();
		return B("/api/investment-context/summary", { signal: e.signal }).then(n).catch(() => {}), () => e.abort();
	}, []), (0, l.useEffect)(() => () => f.current?.abort(), []);
	async function p(e) {
		f.current?.abort();
		let t = new AbortController();
		f.current = t, o(e.ticker), c(null), d("");
		try {
			let n = (await ut(await V("/api/agent/investment-context/explain", { tickers: [e.ticker] }, { signal: t.signal }), { signal: t.signal })).result?.reply?.trim() || "";
			if (!n) throw Error("설명 결과가 비어 있습니다.");
			c({
				ticker: e.ticker,
				reply: n
			});
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") return;
			d(e instanceof Error ? e.message : "Agent 설명을 완료하지 못했습니다.");
		} finally {
			f.current === t && (f.current = null, o(""));
		}
	}
	return r ? null : /* @__PURE__ */ (0, K.jsx)(cn, {
		...e,
		summary: t,
		onDismiss: e.dismissible ? () => {
			i(!0);
			try {
				window.localStorage.setItem(en, "1");
			} catch {}
		} : void 0,
		onExplain: p,
		explainingTicker: a,
		explanation: s,
		explanationError: u
	});
}
//#endregion
//#region src/app/AgentHome.tsx
function un() {
	let e = Ft("agent_home");
	return /* @__PURE__ */ (0, K.jsx)("div", {
		className: "react-home-route",
		"data-agent-home": !0,
		children: /* @__PURE__ */ (0, K.jsxs)("div", {
			className: `agent-home ${e.hasConversation ? "has-conversation" : "is-empty"}`,
			children: [
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "agent-home-left",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("header", {
							className: "home-hero agent-home-hero",
							children: [/* @__PURE__ */ (0, K.jsx)("p", {
								className: "eyebrow",
								children: "Local Investment Research Workspace"
							}), /* @__PURE__ */ (0, K.jsx)("h1", { children: /* @__PURE__ */ (0, K.jsx)($t, { variant: "hero" }) })]
						}),
						/* @__PURE__ */ (0, K.jsx)(q, { workspace: e }),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "home-launcher agent-home-launcher",
							role: "group",
							"aria-label": "빠른 실행",
							children: [
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "launch-tile",
									type: "button",
									onClick: () => e.runQuickAction("briefing"),
									disabled: e.quickBusy === "briefing",
									children: e.quickBusy === "briefing" ? "생성 중" : "오늘 브리핑 생성"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "launch-tile",
									type: "button",
									onClick: () => e.runQuickAction("rss"),
									disabled: e.quickBusy === "rss",
									children: e.quickBusy === "rss" ? "수집 중" : "RSS 수집"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "launch-tile",
									type: "button",
									onClick: () => e.runQuickAction("analysis"),
									children: "기업 분석"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "launch-tile",
									"data-qa": "home-deep-research",
									type: "button",
									onClick: () => e.runQuickAction("deep-research"),
									children: "딥 리서치"
								})
							]
						}),
						/* @__PURE__ */ (0, K.jsx)(ln, {
							mode: "home",
							dismissible: !0
						}),
						e.recentReports.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "review-recent-wrap agent-home-recent",
							children: [/* @__PURE__ */ (0, K.jsx)("span", {
								className: "rv-recent-cap",
								children: "최근 보고서"
							}), /* @__PURE__ */ (0, K.jsx)("div", {
								className: "rv-recent",
								children: e.recentReports.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("button", {
									className: "rv-rc",
									type: "button",
									"data-tooltip": `${e.title || "보고서"}${e.date ? ` · ${e.date}` : ""}`,
									onClick: () => {
										window.location.hash = qe(e);
									},
									children: [/* @__PURE__ */ (0, K.jsx)("span", {
										className: "rv-rc-k",
										children: String(e.type || e.view || "REPORT").toUpperCase()
									}), /* @__PURE__ */ (0, K.jsx)("span", {
										className: "rv-rc-t",
										children: e.title || "제목 없음"
									})]
								}, Je(e, t)))
							})]
						})
					]
				}),
				/* @__PURE__ */ (0, K.jsx)(ze, { workspace: e }),
				/* @__PURE__ */ (0, K.jsx)(Qt, {
					surface: "home",
					pageSize: 20,
					refreshKey: e.workLogRefreshKey,
					collapsible: !0
				})
			]
		})
	});
}
//#endregion
//#region src/app/useContentRevision.ts
var dn = 5e3;
function fn(e) {
	let [t, n] = (0, l.useState)(0), r = (0, l.useRef)(null);
	return (0, l.useEffect)(() => {
		let t = !0, i = 0;
		async function a() {
			if (!(!t || document.hidden)) try {
				let i = await B("/api/content-revisions"), a = Number(i.revisions?.[e] ?? 0);
				if (!t) return;
				r.current === null ? r.current = a : a !== r.current && (r.current = a, n((e) => e + 1));
			} catch {}
		}
		function o() {
			i = window.setTimeout(async () => {
				await a(), t && o();
			}, dn);
		}
		function s() {
			document.hidden || a();
		}
		return a(), o(), document.addEventListener("visibilitychange", s), () => {
			t = !1, window.clearTimeout(i), document.removeEventListener("visibilitychange", s);
		};
	}, [e]), t;
}
//#endregion
//#region src/app/savedListFormat.ts
function pn(e) {
	if (!e.includes("T")) return e.slice(0, 10);
	let t = new Date(e);
	if (Number.isNaN(t.getTime())) return e.slice(0, 10);
	let n = new Date(t.getTime() + 324e5), r = (e) => String(e).padStart(2, "0");
	return `${n.getUTCFullYear()}-${r(n.getUTCMonth() + 1)}-${r(n.getUTCDate())}`;
}
function mn(e) {
	let t = String(e || "").trim();
	if (!t) return "";
	let n = pn(t), r = /^(\d{4})[-.](\d{2})[-.](\d{2})$/.exec(n);
	if (r) return `${r[1]}.${r[2]}.${r[3]}`;
	let i = new Date(t);
	if (Number.isNaN(i.getTime())) return t;
	let a = (e) => String(e).padStart(2, "0");
	return `${i.getFullYear()}.${a(i.getMonth() + 1)}.${a(i.getDate())}`;
}
function hn(e, t) {
	let n = mn(t);
	return n ? `${e}건 · 최근 ${n}` : `${e}건`;
}
function gn(e, t) {
	let n = String(e || "").trim(), r = String(t || "").trim();
	return !n || !r || r === n ? "" : r;
}
//#endregion
//#region src/app/useMarketScope.ts
var _n = {
	selected: [
		"US",
		"KR",
		"EUROPE",
		"JP"
	],
	enabledAt: {},
	updatedAt: "",
	markets: [
		{
			id: "US",
			label: "미국"
		},
		{
			id: "KR",
			label: "한국"
		},
		{
			id: "EUROPE",
			label: "유럽"
		},
		{
			id: "JP",
			label: "일본"
		}
	]
};
function vn() {
	let [e, t] = (0, l.useState)(_n), [n, r] = (0, l.useState)(!1), i = (0, l.useCallback)(async () => {
		try {
			let e = await B("/api/market-scope");
			t({
				..._n,
				...e
			});
		} catch {
			t(_n);
		} finally {
			r(!0);
		}
	}, []);
	return (0, l.useEffect)(() => {
		i();
	}, [i]), {
		scope: e,
		loaded: n,
		reload: i,
		isSelected: (0, l.useCallback)((t) => {
			let n = String(t || "").toUpperCase();
			if (!n || n === "GLOBAL" || n === "UNKNOWN") return !0;
			let r = n === "EU" ? "EUROPE" : n;
			return e.selected.includes(r);
		}, [e.selected])
	};
}
//#endregion
//#region src/app/legacyBridge.ts
function yn() {
	return window.FolioBridge ?? {};
}
//#endregion
//#region src/app/reportReader/ReaderActions.tsx
function bn({ title: e, children: t }) {
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "report-reader-rail-group",
		"aria-label": e,
		children: [/* @__PURE__ */ (0, K.jsx)("p", {
			className: "section-kicker",
			children: e
		}), /* @__PURE__ */ (0, K.jsx)("div", {
			className: "report-reader-rail-actions",
			children: t
		})]
	});
}
function xn({ icon: e, children: t, ...n }) {
	return /* @__PURE__ */ (0, K.jsxs)("button", {
		className: "btn report-action-btn",
		type: "button",
		...n,
		children: [/* @__PURE__ */ (0, K.jsx)(Sn, { name: e }), /* @__PURE__ */ (0, K.jsx)("span", { children: t })]
	});
}
function Sn({ name: e }) {
	return e === "agent" ? /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "report-action-icon",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", { d: "m4 17 6-6-6-6m8 14h8" })
	}) : e === "link" ? /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "report-action-icon",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("path", {
				fill: "currentColor",
				stroke: "none",
				fillRule: "evenodd",
				clipRule: "evenodd",
				d: "M5 2a3 3 0 0 0-3 3v14a3 3 0 0 0 3 3h6.4a6 6 0 0 1 8.6-8.4V5a3 3 0 0 0-3-3H5Zm2 4a1 1 0 0 0 0 2h10a1 1 0 1 0 0-2H7Zm0 4a1 1 0 1 0 0 2h5a1 1 0 1 0 0-2H7Z"
			}),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M20.5 17.4a3 3 0 1 1-.9-2.1" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M20.9 14.1v2.3h-2.3" })
		]
	}) : e === "notion" ? /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "report-action-icon",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", {
			fill: "currentColor",
			stroke: "none",
			d: "M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.139c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z"
		})
	}) : e === "obsidian" ? /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "report-action-icon",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", {
			fill: "currentColor",
			stroke: "none",
			d: "M19.355 18.538a68.967 68.959 0 0 0 1.858-2.954.81.81 0 0 0-.062-.9c-.516-.685-1.504-2.075-2.042-3.362-.553-1.321-.636-3.375-.64-4.377a1.707 1.707 0 0 0-.358-1.05l-3.198-4.064a3.744 3.744 0 0 1-.076.543c-.106.503-.307 1.004-.536 1.5-.134.29-.29.6-.446.914l-.31.626c-.516 1.068-.997 2.227-1.132 3.59-.124 1.26.046 2.73.815 4.481.128.011.257.025.386.044a6.363 6.363 0 0 1 3.326 1.505c.916.79 1.744 1.922 2.415 3.5zM8.199 22.569c.073.012.146.02.22.02.78.024 2.095.092 3.16.29.87.16 2.593.64 4.01 1.055 1.083.316 2.198-.548 2.355-1.664.114-.814.33-1.735.725-2.58l-.01.005c-.67-1.87-1.522-3.078-2.416-3.849a5.295 5.295 0 0 0-2.778-1.257c-1.54-.216-2.952.19-3.84.45.532 2.218.368 4.829-1.425 7.531zM5.533 9.938c-.023.1-.056.197-.098.29L2.82 16.059a1.602 1.602 0 0 0 .313 1.772l4.116 4.24c2.103-3.101 1.796-6.02.836-8.3-.728-1.73-1.832-3.081-2.55-3.831zM9.32 14.01c.615-.183 1.606-.465 2.745-.534-.683-1.725-.848-3.233-.716-4.577.154-1.552.7-2.847 1.235-3.95.113-.235.223-.454.328-.664.149-.297.288-.577.419-.86.217-.47.379-.885.46-1.27.08-.38.08-.72-.014-1.043-.095-.325-.297-.675-.68-1.06a1.6 1.6 0 0 0-1.475.36l-4.95 4.452a1.602 1.602 0 0 0-.513.952l-.427 2.83c.672.59 2.328 2.316 3.335 4.711.09.21.175.43.253.653z"
		})
	}) : /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "report-action-icon",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [/* @__PURE__ */ (0, K.jsx)("path", { d: "m4 12 15-7-7 15-2-6z" }), /* @__PURE__ */ (0, K.jsx)("path", { d: "m10 14 4-4" })]
	});
}
//#endregion
//#region src/app/reportReader/MarkdownRenderer.tsx
function Cn(e) {
	let t = [], n = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g, r = 0;
	for (let i of e.matchAll(n)) i.index !== void 0 && (i.index > r && t.push({
		type: "text",
		value: e.slice(r, i.index)
	}), i[2] ? t.push({
		type: "strong",
		value: i[2]
	}) : i[3] ? t.push({
		type: "code",
		value: i[3]
	}) : i[4] && i[5] && t.push({
		type: "link",
		label: i[4],
		href: i[5]
	}), r = i.index + i[0].length);
	return r < e.length && t.push({
		type: "text",
		value: e.slice(r)
	}), t;
}
function wn(e) {
	return Cn(e).map((e, t) => e.type === "strong" ? /* @__PURE__ */ (0, K.jsx)("strong", { children: e.value }, t) : e.type === "code" ? /* @__PURE__ */ (0, K.jsx)("code", { children: e.value }, t) : e.type === "link" ? /* @__PURE__ */ (0, K.jsx)("a", {
		href: e.href,
		target: "_blank",
		rel: "noreferrer",
		children: e.label
	}, t) : /* @__PURE__ */ (0, K.jsx)("span", { children: e.value }, t));
}
function Tn(e, t) {
	e.length &&= (t.push(/* @__PURE__ */ (0, K.jsx)("p", { children: wn(e.join(" ")) }, `p-${t.length}`)), 0);
}
function En({ markdown: e = "" }) {
	let t = [], n = [], r = e.replace(/\r\n/g, "\n").split("\n"), i = [];
	function a() {
		i.length && (t.push(/* @__PURE__ */ (0, K.jsx)("ul", { children: i.map((e, t) => /* @__PURE__ */ (0, K.jsx)("li", { children: wn(e) }, t)) }, `ul-${t.length}`)), i = []);
	}
	for (let e of r) {
		let r = e.trimEnd().trim();
		if (!r) {
			Tn(n, t), a();
			continue;
		}
		let o = r.match(/^(#{2,4})\s+(.+)$/);
		if (o) {
			Tn(n, t), a();
			let e = o[1].length, r = wn(o[2]);
			e === 2 ? t.push(/* @__PURE__ */ (0, K.jsx)("h2", { children: r }, `h-${t.length}`)) : e === 3 ? t.push(/* @__PURE__ */ (0, K.jsx)("h3", { children: r }, `h-${t.length}`)) : t.push(/* @__PURE__ */ (0, K.jsx)("h4", { children: r }, `h-${t.length}`));
			continue;
		}
		let s = r.match(/^[-*]\s+(.+)$/);
		if (s) {
			Tn(n, t), i.push(s[1]);
			continue;
		}
		n.push(r);
	}
	return Tn(n, t), a(), /* @__PURE__ */ (0, K.jsx)("div", {
		className: "react-markdown markdown-brief report-body",
		children: t
	});
}
//#endregion
//#region src/app/reportReader/ReportBody.tsx
function Dn(e = "") {
	let t = e.replace(/\r\n/g, "\n"), n = /^#{1,3}\s*(?:참고\s*자료|참고자료|Sources Used|Sources)\s*$/gim.exec(t);
	return !n || n.index === void 0 ? e : t.slice(0, n.index).trim();
}
function On({ markdown: e = "", marketScope: t = "both", briefing: n, sourcePanelHtml: r = "" }) {
	let i = (0, l.useRef)(null), a = yn(), o = Dn(e), s = a.renderMarkdown?.(o);
	return (0, l.useEffect)(() => {
		let e = i.current;
		if (!(!e || !n || !a.renderBriefingVisuals)) return a.renderBriefingVisuals(e, n), () => a.cleanupBriefingVisuals?.();
	}, [o, n]), s === void 0 ? /* @__PURE__ */ (0, K.jsx)(En, { markdown: o }) : /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("article", {
		ref: i,
		className: "markdown-brief report-body",
		"data-market-scope": t,
		dangerouslySetInnerHTML: { __html: s }
	}), r && /* @__PURE__ */ (0, K.jsx)("div", { dangerouslySetInnerHTML: { __html: r } })] });
}
//#endregion
//#region src/app/reportReader/HypothesisReviewCard.tsx
var kn = {
	fresh: "최신",
	due: "검토 예정",
	stale: "검토 지연",
	unknown: "검토 이력 없음"
};
function An(e) {
	return e ? e.slice(0, 10) : "—";
}
function jn(e) {
	return new Promise((t) => window.setTimeout(t, e));
}
function Mn(e) {
	return "id" in e && "status" in e;
}
async function Nn(e) {
	let t = e;
	for (; I(t.status);) await jn(1e3), t = await B(`/api/jobs/${encodeURIComponent(t.id)}`);
	if (t.status !== "done") throw Error(t.message || t.error || "가설 검토 작업에 실패했습니다.");
	return t;
}
function Pn({ identity: e, noteExists: t, refreshKey: n, agentAvailable: r = !0, onRequestAgent: i }) {
	let [a, o] = (0, l.useState)(null), [s, c] = (0, l.useState)(""), [u, d] = (0, l.useState)(!1);
	(0, l.useEffect)(() => {
		if (o(null), !t || !e.ticker) return;
		let n = new AbortController();
		return c("검토 상태를 불러오는 중..."), H(e.id, { signal: n.signal }).then((e) => {
			o(e), c("");
		}).catch((e) => {
			n.signal.aborted || c(e instanceof Error ? e.message : "검토 상태를 불러오지 못했습니다.");
		}), () => n.abort();
	}, [
		e.id,
		e.ticker,
		t,
		n
	]);
	let f = (0, l.useMemo)(() => a?.reviewState.checkpoints.find((e) => e.state === "due" || e.state === "open") || null, [a]);
	async function p(t) {
		if (!(!a || !e.ticker || u)) {
			d(!0), c("체크포인트를 확인하는 중...");
			try {
				let n = await U(e.ticker, {
					noteId: e.id,
					checkpointId: t.id,
					state: "checked",
					expectedRevision: a.reviewState.revision
				});
				o(n), c("체크포인트를 확인했습니다.");
			} catch (e) {
				c(e instanceof Error ? e.message : "체크포인트 확인에 실패했습니다.");
			} finally {
				d(!1);
			}
		}
	}
	async function m() {
		if (!(!a?.thesis || !e.ticker || u)) {
			d(!0), c("최신 외부 근거로 가설을 검토하는 중...");
			try {
				let t = await ee(e.ticker);
				Mn(t) && await Nn(t);
				let n = await H(e.id);
				o(n), c("최신 근거 검토를 완료했습니다.");
			} catch (e) {
				c(e instanceof Error ? e.message : "최신 근거 검토에 실패했습니다.");
			} finally {
				d(!1);
			}
		}
	}
	let h = "";
	return t === null ? h = "노트 상태를 확인하는 중..." : t ? e.ticker || (h = "티커가 없어 Thesis와 연결할 수 없습니다.") : h = "아직 저장된 노트가 없습니다.", /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "hypothesis-review-card",
		"aria-label": "가설 검토 상태",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "hypothesis-review-head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
					className: "section-kicker",
					children: "Hypothesis Review"
				}), /* @__PURE__ */ (0, K.jsx)("strong", { children: "가설 검토 상태" })] }), a && /* @__PURE__ */ (0, K.jsx)("span", {
					className: `hypothesis-freshness is-${a.reviewState.freshness}`,
					children: kn[a.reviewState.freshness]
				})]
			}),
			h ? /* @__PURE__ */ (0, K.jsx)("p", {
				className: "hypothesis-review-empty",
				children: h
			}) : a ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
				!a.thesis && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "hypothesis-review-empty",
					children: "연결된 Thesis가 없습니다."
				}),
				!a.latestDelta && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "hypothesis-review-empty",
					children: "최신 Delta가 없습니다. 최신 근거 검토를 명시적으로 실행하세요."
				}),
				/* @__PURE__ */ (0, K.jsxs)("dl", {
					className: "hypothesis-review-metrics",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "최근 검토" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: An(a.reviewState.lastReviewedAt) })] }),
						/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "다음 검토" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: An(a.reviewState.nextReviewAt) })] }),
						/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "반대 근거" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a.latestDelta?.counterEvidenceCount ?? 0 })] }),
						/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "예정 체크" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a.checkpointCounts.due + a.checkpointCounts.open })] })
					]
				}),
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "hypothesis-review-actions",
					children: [
						/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							onClick: m,
							disabled: !a.thesis || u,
							children: u ? "검토 중..." : "최신 근거로 검토"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							onClick: () => f && p(f),
							disabled: !f || u,
							children: u ? "확인 중..." : "체크포인트 확인"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							onClick: i,
							disabled: !r,
							children: "Agent에게 설명 요청"
						})
					]
				}),
				!f && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "hypothesis-review-empty",
					children: "확인할 체크포인트가 없습니다."
				}),
				!r && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "hypothesis-review-empty",
					children: "Agent를 사용할 수 없습니다. 규칙 기반 상태는 계속 확인할 수 있습니다."
				})
			] }) : /* @__PURE__ */ (0, K.jsx)("p", {
				className: "hypothesis-review-empty",
				children: s || "검토 상태를 준비하고 있습니다."
			}),
			s && a && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "hypothesis-review-status",
				children: s
			}),
			/* @__PURE__ */ (0, K.jsx)("p", {
				className: "hypothesis-layer-notice",
				children: "사용자 노트는 hypothesis이며 evidence가 아닙니다. Canonical 보고서는 변경되지 않습니다."
			})
		]
	});
}
//#endregion
//#region src/app/reportReader/PersonalOverlayView.tsx
function Fn(e) {
	return e.length ? /* @__PURE__ */ (0, K.jsx)("ul", { children: e.map((e, t) => /* @__PURE__ */ (0, K.jsx)("li", { children: e }, `${e}-${t}`)) }) : /* @__PURE__ */ (0, K.jsx)("p", { children: "기록 없음" });
}
function In({ overlay: e, staleQa: t }) {
	return e ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-personal-overlay",
		"data-personal-overlay-state": e.revisionState,
		children: [
			e.revisionState === "stale" && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-overlay-stale",
				"data-qa": t,
				role: "status",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "이 Overlay는 오래된 Canonical 기준입니다." }), /* @__PURE__ */ (0, K.jsx)("span", { children: "현재 보고서 revision과 생성 당시 revision이 다르므로 다시 연결해 확인하세요." })]
			}),
			e.revisionState === "legacy_unknown" && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "topicrpt-layer-note",
				children: "생성 기준 revision을 확인할 수 없는 레거시 Overlay입니다."
			}),
			e.markdown ? /* @__PURE__ */ (0, K.jsx)(On, { markdown: e.markdown }) : /* @__PURE__ */ (0, K.jsx)("p", {
				className: "report-note-empty",
				children: "저장된 개인 해석 본문이 없습니다."
			}),
			/* @__PURE__ */ (0, K.jsx)("h4", { children: "반대 근거와 충돌" }),
			Fn([...e.counterEvidence, ...e.contradictions]),
			/* @__PURE__ */ (0, K.jsx)("h4", { children: "불확실성과 다음 질문" }),
			Fn([...e.uncertainties, ...e.personalQuestions])
		]
	}) : /* @__PURE__ */ (0, K.jsx)("p", {
		className: "report-note-empty",
		children: "생성된 Personal Overlay가 없습니다."
	});
}
//#endregion
//#region src/app/reportReader/FolioNotePanel.tsx
var Ln = [
	"## 현재 관점",
	"",
	"## 왜 중요한가",
	"",
	"## 근거",
	"",
	"## 반대 근거",
	"",
	"## 다음 체크포인트",
	"",
	"## 결정/업데이트 로그",
	""
].join("\n"), Rn = [
	"떠오르는 생각을 자유롭게 정리해보세요. 막연한 느낌이나 궁금증 한 줄만 작성해도 됩니다.",
	"",
	"예시: \"이 주식은 앞으로 받을 수혜가 커 보여서 관심 있음\"",
	"예시: \"가격이 너무 오른 것 같은데 그래도 들고 갈 만한가?\""
].join("\n"), zn = "[대화]", Bn = "[투자 노트]";
function Vn(e) {
	return new Promise((t) => window.setTimeout(t, e));
}
async function Hn(e) {
	let t = e;
	for (; I(t.status);) await Vn(1e3), t = await B(`/api/jobs/${encodeURIComponent(t.id)}`);
	if (t.status !== "done") throw Error(t.message || t.error || "Agent 작업에 실패했습니다.");
	return t;
}
function Un(e) {
	let t = String(e || ""), n = t.indexOf(Bn), r = (e) => e.replace(/^\s*\[대화\]\s*/, "").trim();
	return n < 0 ? {
		message: r(t),
		note: ""
	} : {
		message: r(t.slice(0, n)),
		note: t.slice(n + 7).trim()
	};
}
function Wn(e, t) {
	let n = t.trim();
	if (!n) return e;
	let r = e[e.length - 1];
	return r?.role === "user" && r.body.trim() === n ? e : [...e, {
		role: "user",
		body: n,
		createdAt: (/* @__PURE__ */ new Date()).toISOString()
	}];
}
function Gn(e, t, n = "") {
	return [...e, {
		role: "agent",
		body: t,
		summary: n || "Agent 답변",
		createdAt: (/* @__PURE__ */ new Date()).toISOString()
	}];
}
function Kn(e, t, n, r, i = [], a = []) {
	let o = i.slice(-8).map((e, t) => `${t + 1}. ${e.body}`).join("\n"), s = a.slice(-8).map((e, t) => {
		let { message: n, note: r } = Un(e.body);
		return `${t + 1}. ${e.summary || "Agent"}: ${n || (r ? "(투자 노트 전체를 업데이트함)" : "")}`;
	}).join("\n\n");
	return [
		"현재 열린 보고서와 Folio OS Market Memory를 함께 참고해, 사용자와 대화하면서 투자 노트를 완성해줘.",
		"사용자가 적은 생각은 근거가 아니라 hypothesis다. 옹호하지 말고 검증 가능한 투자 노트로 다듬어줘.",
		"없는 사실은 지어내지 말고, 추가 확인 필요로 표시해줘.",
		"사용자 판단과 Agent가 제안하는 해석을 구분하고, 반대 근거와 다음 체크포인트를 포함해줘.",
		"사용자가 `>`로 인용한 문장이 있으면 그 문장에 대한 질문/첨삭 요청으로 이해하고 해당 부분을 중심으로 답해줘.",
		"응답 형식을 반드시 지켜줘:",
		`1) ${zn} 아래에 사용자에게 하는 짧은 대화 답변(무엇을 반영/수정했는지, 확인하고 싶은 점)을 2~5문장으로 써줘.`,
		`2) 노트를 새로 만들거나 수정할 내용이 있으면 ${Bn} 아래에 투자 노트 전체 Markdown을 써줘. 단순 질문에 답만 하는 경우에는 ${Bn} 부분을 생략하고 기존 노트를 유지해줘.`,
		"기존 정리본이 있으면 전체를 갈아엎기보다 필요한 부분을 업데이트하고, 결정/업데이트 로그에 변경 이유를 남겨줘.",
		"투자 노트는 아래 큰 구조를 유지하되, 각 섹션은 초보 투자자가 바로 이해할 수 있게 짧고 명확하게 작성해줘.",
		Ln,
		`노트 제목: ${e.title}`,
		`연결 문서: ${r || e.linkedReports?.[0] || e.title}`,
		`보고서 종류: ${e.reportKind || e.noteType || "report"}`,
		`보고서 ID: ${e.reportId || e.id}`,
		e.ticker ? `티커: ${e.ticker}` : "",
		e.topic ? `주제: ${e.topic}` : "",
		n.trim() ? `이번 사용자 메시지:\n${n.trim()}` : "",
		o ? `이전 사용자 메시지 기록:\n${o}` : "",
		s ? `이전 Agent 대화 기록:\n${s}` : "",
		t.trim() ? `현재 정리된 투자 노트:\n${t.trim()}` : ""
	].filter(Boolean).join("\n\n");
}
function qn(e, t) {
	let n = String(t || e || "note"), r = 2166136261;
	for (let e = 0; e < n.length; e += 1) r ^= n.charCodeAt(e), r = Math.imul(r, 16777619) >>> 0;
	return `${e}-${r.toString(36)}`;
}
function Jn({ identity: e, linkedTitle: t, overlay: n = null }) {
	let [r, i] = (0, l.useState)(""), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(""), [u, d] = (0, l.useState)([]), [f, p] = (0, l.useState)([]), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)("chat"), [v, y] = (0, l.useState)([]), [b, x] = (0, l.useState)(!1), [S, C] = (0, l.useState)([]), [w, T] = (0, l.useState)(null), [E, D] = (0, l.useState)(0), O = (0, l.useRef)(null), k = S.includes("agent_assisted"), A = (0, l.useMemo)(() => [...u, ...f].sort((e, t) => String(e.createdAt || "").localeCompare(String(t.createdAt || ""))), [u, f]);
	(0, l.useEffect)(() => {
		let t = !0;
		async function n() {
			h("불러오는 중..."), y([]), i(""), o(""), c(""), d([]), p([]), T(null);
			try {
				let n = await B(`/api/investment-notes/${encodeURIComponent(e.id)}`);
				if (!t) return;
				i(n.body || ""), d(n.rawThoughts || []), p(n.interactionLog || []), C(n.tags || []), T(!0), h(n.updatedAt ? `저장됨: ${n.updatedAt}` : "Folio 로컬 노트를 불러왔습니다.");
			} catch {
				if (!t) return;
				C([]), T(!1), h("생각 한 줄에서 시작하세요.");
			}
			try {
				let n = await B(`/api/investment-notes/linked?${new URLSearchParams({
					ticker: e.ticker || "",
					topic: e.topic || "",
					reportId: e.reportId || ""
				})}`);
				if (!t) return;
				y(n.notes || []);
			} catch {
				if (!t) return;
				y([]);
			}
		}
		return n(), () => {
			t = !1;
		};
	}, [
		e.id,
		e.reportId,
		e.ticker,
		e.topic
	]), (0, l.useEffect)(() => {
		let e = O.current;
		e && (e.scrollTop = e.scrollHeight);
	}, [A.length, g]);
	async function j(t, n, r, i = S) {
		let a = await V("/api/investment-notes", {
			...e,
			body: t,
			rawThoughts: n,
			interactionLog: r,
			tags: i
		});
		return C(a.tags || []), T(!0), D((e) => e + 1), a;
	}
	function M() {
		let e = a.trim(), t = s.trim();
		return t && e ? `> ${t}\n\n${e}` : t ? `> ${t}` : e;
	}
	function N() {
		let e = window.getSelection()?.toString().replace(/\s+/g, " ").trim() || "";
		e.length >= 2 && c(e.slice(0, 400));
	}
	async function P() {
		let e = M();
		if (e) {
			h("저장 중...");
			try {
				let t = Wn(u, e), n = await j(r, t, f);
				d(n.rawThoughts || t), p(n.interactionLog || f), o(""), c(""), h("생각을 기록했습니다. Agent 정리는 나중에 요청할 수 있습니다.");
			} catch (e) {
				h(e instanceof Error ? `저장 실패: ${e.message}` : "저장 실패");
			}
		}
	}
	async function F() {
		let n = M();
		if (!n || b) return;
		x(!0), h("Agent가 응답을 준비하는 중...");
		let a = Wn(u, n);
		d(a), o(""), c("");
		try {
			let o = await Hn(await V("/api/agent/chat", {
				message: Kn(e, r, n, t, a, f),
				context: {
					surface: "folio_note",
					viewId: "investment_note",
					reportKind: e.reportKind || e.noteType || "",
					reportId: e.reportId || e.id || "",
					ticker: e.ticker || "",
					topic: e.topic || "",
					noteId: e.id
				},
				options: { effort: "high" }
			})), s = o.result || {}, c = String(s.reply || "").trim();
			if (!c) throw Error(o.message || "Agent가 응답을 반환하지 않았습니다.");
			let { note: l } = Un(c), u = Gn(f, c, s.notice || (l ? "투자 노트 업데이트" : "Agent 답변")), m = l || r, g = await j(m, a, u, l ? Array.from(/* @__PURE__ */ new Set([...S, "agent_assisted"])) : S);
			i(g.body || m), d(g.rawThoughts || a), p(g.interactionLog || u), h(l ? "Agent가 투자 노트를 업데이트했습니다. 완성본은 연결 자료 탭에서 확인하세요." : "Agent가 답변했습니다. 노트 본문은 그대로 유지했습니다.");
		} catch (e) {
			try {
				await j(r, a, f);
			} catch {}
			h(e instanceof Error ? `AI 정리 실패: ${e.message}` : "AI 정리 실패");
		} finally {
			x(!1);
		}
	}
	function I() {
		_("chat"), o("현재 freshness, 최신 verdict, 반대 근거, 체크포인트 상태가 무엇을 의미하는지 설명해줘."), h("설명 요청을 준비했습니다. 내용을 확인한 뒤 Agent 버튼을 눌러 실행하세요.");
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-note-panel",
		"data-report-note-panel": !0,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "report-note-head react-note-panel-head",
				children: [/* @__PURE__ */ (0, K.jsx)("p", {
					className: "section-kicker",
					children: "투자 생각 정리"
				}), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "report-note-tabs",
					role: "tablist",
					"aria-label": "투자 노트 모드",
					children: [["chat", "작성"], ["links", "연결 자료"]].map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("button", {
						className: "report-note-tab",
						type: "button",
						"aria-pressed": g === e,
						onClick: () => _(e),
						children: t
					}, e))
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)(Pn, {
				identity: e,
				noteExists: w,
				refreshKey: E,
				onRequestAgent: I
			}),
			g === "chat" && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "report-note-chat",
				children: [A.length === 0 ? /* @__PURE__ */ (0, K.jsx)("p", {
					className: "report-note-empty report-note-chat-empty",
					children: "먼저 떠오르는 생각 한 줄을 남겨보세요. Agent가 열린 보고서와 Market Memory를 참고해 투자 노트로 정리해줍니다."
				}) : /* @__PURE__ */ (0, K.jsx)("ol", {
					className: "report-note-chat-list",
					ref: O,
					onMouseUp: N,
					children: A.map((e, t) => {
						let n = e.role === "agent", { message: r, note: i } = n ? Un(e.body) : {
							message: e.body,
							note: ""
						};
						return /* @__PURE__ */ (0, K.jsxs)("li", {
							className: `report-note-chat-item ${n ? "is-agent" : "is-user"}`,
							children: [
								/* @__PURE__ */ (0, K.jsxs)("span", {
									className: "report-note-history-meta",
									children: [
										n ? "Agent" : "사용자",
										" ",
										e.createdAt || ""
									]
								}),
								r && /* @__PURE__ */ (0, K.jsx)("p", {
									className: "report-note-chat-text",
									children: r
								}),
								i && /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "report-note-chat-note",
									children: [/* @__PURE__ */ (0, K.jsx)("span", {
										className: "report-note-chat-note-label",
										children: "완성된 투자 노트"
									}), /* @__PURE__ */ (0, K.jsx)(On, { markdown: i })]
								})
							]
						}, `${e.role}-${e.createdAt || t}-${t}`);
					})
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "report-note-composer",
					children: [
						s && /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "report-note-quote-bar",
							children: [
								/* @__PURE__ */ (0, K.jsx)("span", {
									className: "report-note-quote-label",
									children: "인용"
								}),
								/* @__PURE__ */ (0, K.jsx)("p", { children: s }),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn btn--icon btn--sm",
									type: "button",
									onClick: () => c(""),
									"aria-label": "인용 지우기",
									children: "×"
								})
							]
						}),
						/* @__PURE__ */ (0, K.jsx)("textarea", {
							className: "report-note-thought-editor",
							value: a,
							onChange: (e) => o(e.currentTarget.value),
							rows: 3,
							placeholder: Rn,
							"aria-label": `${e.title} 사용자의 생각`
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "report-note-composer-actions",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn report-note-secondary-action",
								type: "button",
								onClick: P,
								disabled: b || !M(),
								children: "생각만 기록"
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn btn--primary report-note-primary-action",
								type: "button",
								onClick: F,
								disabled: b || !M(),
								children: b ? "Agent가 정리 중" : "Agent와 투자 노트 정리하기"
							})]
						}),
						/* @__PURE__ */ (0, K.jsx)("p", {
							className: "report-note-composer-hint",
							children: "Agent 답변이나 완성본에서 문장을 드래그하면 인용해서 이어서 물어볼 수 있습니다."
						})
					]
				})]
			}),
			g === "links" && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "report-note-links",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-note-final",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "report-note-section-label",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "정리된 투자 노트" }), /* @__PURE__ */ (0, K.jsx)("span", { children: r.trim() ? `읽기 전용 완성본입니다. 수정은 작성 탭에서 Agent와 대화로 진행하세요.${k ? " (Agent 정리본)" : ""}` : "작성 탭에서 Agent와 정리하면 여기에 완성본이 표시됩니다." })]
						}), r.trim() ? /* @__PURE__ */ (0, K.jsx)("div", {
							className: "report-note-final-body",
							children: /* @__PURE__ */ (0, K.jsx)(On, { markdown: r })
						}) : /* @__PURE__ */ (0, K.jsx)("p", {
							className: "report-note-empty",
							children: "아직 완성된 투자 노트가 없습니다."
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						className: "report-note-link-head",
						children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: t || e.linkedReports?.[0] || e.title }), "에 연결된 Folio 노트와 참고 정보입니다."]
					}),
					v.length > 0 ? /* @__PURE__ */ (0, K.jsx)("ul", {
						className: "report-note-link-list",
						children: v.slice(0, 8).map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-note-link-title",
							children: e.title || "투자 노트"
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-note-link-meta",
							children: e.ticker || e.noteType || "note"
						})] }, e.id || e.title))
					}) : /* @__PURE__ */ (0, K.jsx)("p", {
						className: "report-note-empty",
						children: "아직 연결된 노트가 없습니다."
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-note-layer",
						children: [/* @__PURE__ */ (0, K.jsx)("p", {
							className: "section-kicker",
							children: "참고 해석"
						}), /* @__PURE__ */ (0, K.jsx)(In, { overlay: n })]
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "report-note-foot",
				children: m && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "report-note-status",
					children: m
				})
			})
		]
	});
}
//#endregion
//#region src/app/reportReader/ReportReaderShell.tsx
function Yn({ eyebrow: e, title: t, meta: n, breadcrumb: r, actionSlot: i, noteSlot: a, noteIdentity: o, noteLinkedTitle: s, noteOverlay: c, agentContext: u, onClose: d, children: f }) {
	let [p, m] = (0, l.useState)(!1), h = (0, l.useRef)(null), g = (0, l.useRef)(null), _ = (0, l.useRef)(null), v = (0, l.useRef)(null), y = (0, l.useId)(), b = a ?? (o ? /* @__PURE__ */ (0, K.jsx)(Jn, {
		identity: o,
		linkedTitle: s || t,
		overlay: c || null
	}) : null), x = u ? JSON.stringify(u) : "", S = [
		"report-reader-stage",
		!i && !b ? "no-side" : "",
		i ? "" : "no-rail",
		b ? "" : "no-note"
	].filter(Boolean).join(" ");
	(0, l.useEffect)(() => {
		if (!x || !u) return;
		let e = String(u.viewId || ""), t = e === "topicrpt" ? "deep-research" : e;
		t && Qe(t, u);
	}, [u, x]), (0, l.useEffect)(() => {
		h.current?.focus({ preventScroll: !0 });
	}, [t]);
	let C = (0, l.useCallback)(() => {
		m(!1), window.requestAnimationFrame(() => g.current?.focus({ preventScroll: !0 }));
	}, []);
	return (0, l.useEffect)(() => {
		if (!p) return;
		v.current?.focus({ preventScroll: !0 });
		let e = _.current, t = (t) => {
			if (t.key === "Escape") {
				t.preventDefault(), t.stopPropagation(), C();
				return;
			}
			if (t.key !== "Tab" || !e) return;
			let n = Array.from(e.querySelectorAll("button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex=\"-1\"])")).filter((e) => e.getClientRects().length > 0);
			if (!n.length) return;
			let r = n[0], i = n[n.length - 1];
			t.shiftKey && document.activeElement === r ? (t.preventDefault(), i.focus()) : !t.shiftKey && document.activeElement === i && (t.preventDefault(), r.focus());
		};
		return document.addEventListener("keydown", t, !0), () => document.removeEventListener("keydown", t, !0);
	}, [C, p]), (0, l.useEffect)(() => {
		let e = (e) => {
			e.key !== "Escape" || p || !d || (e.target instanceof Element ? e.target : null)?.closest("[role=\"dialog\"][aria-modal=\"true\"]") || (e.preventDefault(), d());
		};
		return document.addEventListener("keydown", e), () => document.removeEventListener("keydown", e);
	}, [p, d]), /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "report-reader-shell report-reader-inline",
		"data-report-reader-shell": !0,
		children: [/* @__PURE__ */ (0, K.jsx)("div", {
			className: "reader-breadcrumb report-reader-breadcrumb",
			children: r
		}), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: S,
			children: [
				/* @__PURE__ */ (0, K.jsxs)("section", {
					ref: h,
					className: "report-reader-dialog report-reader-main",
					"aria-labelledby": y,
					tabIndex: -1,
					children: [/* @__PURE__ */ (0, K.jsx)("div", {
						className: "report-reader-head",
						children: d && /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--icon icon-btn",
							type: "button",
							onClick: d,
							"aria-label": "리더 닫기",
							"data-qa": "dr-report-close",
							"data-tooltip": "닫기",
							"data-tooltip-pos": "left",
							children: "×"
						})
					}), /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-reader-body",
						children: [/* @__PURE__ */ (0, K.jsxs)("section", {
							className: "report-hero react-report-hero",
							children: [
								e && /* @__PURE__ */ (0, K.jsx)("p", {
									className: "report-kicker",
									children: e
								}),
								/* @__PURE__ */ (0, K.jsx)("h1", {
									id: y,
									children: t
								}),
								n && /* @__PURE__ */ (0, K.jsx)("p", {
									className: "report-hero-meta",
									children: n
								})
							]
						}), /* @__PURE__ */ (0, K.jsx)("div", {
							className: "headline react-report-card",
							children: f
						})]
					})]
				}),
				i && /* @__PURE__ */ (0, K.jsx)("aside", {
					className: "report-reader-rail",
					"aria-label": "보고서 조작 패널",
					children: i
				}),
				b && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
					ref: g,
					className: p ? "report-note-grip is-open" : "report-note-grip",
					type: "button",
					"aria-label": "투자 노트 열기",
					"aria-controls": "report-reader-note-panel",
					"aria-expanded": p,
					"data-qa": "reader-note-open",
					onClick: () => m(!0)
				}), /* @__PURE__ */ (0, K.jsx)("aside", {
					ref: _,
					id: "report-reader-note-panel",
					className: p ? "report-note-panel is-open" : "report-note-panel",
					"aria-label": "투자 노트",
					role: p ? "dialog" : void 0,
					"aria-modal": p ? !0 : void 0,
					children: /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-note-inner",
						children: [/* @__PURE__ */ (0, K.jsx)("button", {
							ref: v,
							className: "btn btn--icon report-note-mobile-close",
							type: "button",
							"aria-label": "투자 노트 닫기",
							"data-qa": "reader-note-close",
							onClick: C,
							children: "×"
						}), b]
					})
				})] })
			]
		})]
	});
}
//#endregion
//#region src/app/RouteHero.tsx
function Xn({ eyebrow: e, title: t, description: n, actions: r }) {
	return /* @__PURE__ */ (0, K.jsxs)("header", {
		className: "react-route-hero",
		children: [/* @__PURE__ */ (0, K.jsxs)("div", {
			className: "react-route-hero-copy",
			children: [
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "react-route-hero-eyebrow",
					children: e
				}),
				/* @__PURE__ */ (0, K.jsx)("h1", { children: t }),
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "react-route-hero-description",
					children: n
				})
			]
		}), r && /* @__PURE__ */ (0, K.jsx)("div", {
			className: "react-route-hero-actions",
			children: r
		})]
	});
}
//#endregion
//#region src/app/deepResearchPayload.ts
var Zn = /^sc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
function Qn(e) {
	return `#/deep-research/collections/${encodeURIComponent(e)}`;
}
function $n(e) {
	return `#/deep-research/${encodeURIComponent(e)}`;
}
function er(e) {
	let t = e.replace(/^#\/?/, "");
	if (t === "deep-research" || t === "deep-research/") return {
		kind: "list",
		id: "",
		malformed: !1
	};
	let n = t.match(/^deep-research\/collections\/(.+)$/);
	if (n) try {
		let e = decodeURIComponent(n[1]);
		return Zn.test(e) ? {
			kind: "collection",
			id: e,
			malformed: !1
		} : {
			kind: "collection",
			id: "",
			malformed: !0
		};
	} catch {
		return {
			kind: "collection",
			id: "",
			malformed: !0
		};
	}
	let r = t.match(/^deep-research\/(.+)$/);
	if (!r) return {
		kind: "list",
		id: "",
		malformed: !1
	};
	try {
		let e = decodeURIComponent(r[1]);
		return e ? {
			kind: "report",
			id: e,
			malformed: !1
		} : {
			kind: "report",
			id: "",
			malformed: !0
		};
	} catch {
		return {
			kind: "report",
			id: "",
			malformed: !0
		};
	}
}
function tr(e) {
	return typeof e == "object" && !!e && !Array.isArray(e);
}
function J(e) {
	return typeof e == "string" ? e : "";
}
function nr(e) {
	return typeof e == "number" && Number.isFinite(e) ? e : null;
}
function rr(e) {
	return Array.isArray(e) ? e.filter((e) => typeof e == "string") : [];
}
function ir(e) {
	if (typeof e != "string" || !e.trim()) return "";
	try {
		let t = new URL(e);
		return t.protocol === "http:" || t.protocol === "https:" ? t.href : "";
	} catch {
		return "";
	}
}
function ar(e) {
	return J(e).trim().toLowerCase().replace(/[\s_-]+/g, "");
}
function or(e) {
	if (!tr(e)) return null;
	let t = nr(e.number), n = J(e.hash);
	return t !== null || n ? {
		number: t,
		hash: n
	} : null;
}
function sr(e) {
	return tr(e) ? Object.fromEntries(Object.entries(e).filter((e) => typeof e[1] == "number" && Number.isFinite(e[1]))) : {};
}
function cr(e, t = !1) {
	if (!tr(e)) return {};
	let n = {};
	for (let [r, i] of Object.entries(e)) tr(i) && (n[r] = {
		label: J(i.label),
		question: t ? J(i.question) : "",
		count: nr(i.count) ?? 0,
		level: J(i.level)
	});
	return n;
}
function lr(e) {
	if (!tr(e)) return null;
	let t = tr(e.deepResearch) ? e.deepResearch : {}, n = Array.isArray(e.analysisAxes) ? e.analysisAxes.filter(tr).map((e) => ({
		key: J(e.key),
		label: J(e.label),
		questions: rr(e.questions)
	})).filter((e) => e.key || e.label) : [];
	return {
		topic: J(e.topic),
		reportType: J(e.reportType),
		userIntent: J(e.userIntent),
		researchQuestions: rr(e.researchQuestions),
		analysisAxes: n,
		searchQueries: rr(e.searchQueries),
		expectedSections: rr(e.expectedSections),
		dataGapsLikely: rr(e.dataGapsLikely),
		falsificationTriggers: rr(t.falsificationTriggers)
	};
}
function ur(e) {
	if (!tr(e)) return null;
	let t = cr(e.axisCoverage), n = cr(e.questionCoverage, !0);
	return {
		totalDocs: nr(e.totalDocs) ?? 0,
		roleCounts: sr(e.roleCounts),
		axisCoverage: Object.fromEntries(Object.entries(t).map(([e, t]) => [e, {
			label: t.label,
			count: t.count,
			level: t.level
		}])),
		questionCoverage: Object.fromEntries(Object.entries(n).map(([e, t]) => [e, {
			question: t.question,
			count: t.count,
			level: t.level
		}])),
		dataGaps: rr(e.dataGaps),
		memoryCount: nr(e.memoryCount) ?? 0
	};
}
function dr(e) {
	return Array.isArray(e) ? e.filter(tr).map((e) => ({
		id: J(e.id),
		title: J(e.title),
		source: J(e.source),
		date: J(e.date),
		role: J(e.role),
		axis: J(e.axis),
		confidence: J(e.confidence),
		url: ir(e.url)
	})).filter((e) => !!(e.id && (e.title || e.source))) : [];
}
function fr(e) {
	return Array.isArray(e) ? e.filter(tr).filter((e) => {
		let t = J(e.artifactType).toLowerCase(), n = J(e.type).toLowerCase(), r = J(e.evidenceRole).toLowerCase(), i = J(e.sourceLayer ?? e.source_layer).toLowerCase(), a = ar(e.generatedBy ?? e.generated_by);
		return t !== "user_note" && n !== "user_note" && r !== "hypothesis" && i !== "hypothesis" && i !== "primary_processed" && a !== "folioos";
	}).map((e) => ({
		sourceId: J(e.sourceId),
		title: J(e.title),
		source: J(e.source),
		date: J(e.date),
		evidenceRole: J(e.evidenceRole),
		reliability: J(e.reliability),
		usedInSections: rr(e.usedInSections),
		url: ir(e.url),
		artifactType: J(e.artifactType),
		artifactId: J(e.artifactId),
		path: J(e.path),
		axisKey: J(e.axisKey),
		researchQuestionId: J(e.researchQuestionId),
		researchRound: nr(e.researchRound)
	})).filter((e) => !!(e.sourceId && (e.title || e.source))) : [];
}
function pr(e) {
	return Array.isArray(e) ? e.filter(tr).map((e) => ({
		id: J(e.id),
		severity: J(e.severity),
		description: J(e.description),
		suggestedAction: J(e.suggestedAction),
		resolved: e.resolved === !0
	})).filter((e) => !!(e.id && e.description)) : [];
}
function mr(e) {
	return !tr(e) || ![
		"score",
		"grade",
		"status",
		"warnings",
		"suggestedFixes"
	].some((t) => t in e) ? null : {
		score: nr(e.score),
		grade: J(e.grade),
		status: J(e.status),
		warnings: rr(e.warnings),
		suggestedFixes: rr(e.suggestedFixes)
	};
}
function hr(e) {
	if (!tr(e) || !tr(e.resolution)) return null;
	let t = e.resolution, n = tr(e.zeroEvidence) ? e.zeroEvidence : {}, r = tr(t.providerGenerations) ? t.providerGenerations : {}, i = Array.isArray(t.unusableCandidates) ? t.unusableCandidates.filter(tr).map((e) => ({
		candidateId: J(e.candidateId),
		reason: J(e.reason)
	})).filter((e) => e.candidateId) : [];
	return {
		schemaVersion: nr(t.schemaVersion),
		collectionId: J(t.collectionId),
		collectionRevision: nr(t.collectionRevision),
		collectionDefinitionHash: J(t.collectionDefinitionHash),
		eligibleTotal: nr(t.eligibleTotal),
		candidateCap: nr(t.candidateCap),
		resolvedCandidateIds: rr(t.resolvedCandidateIds),
		executionUniverseIds: rr(t.executionUniverseIds),
		selectedEvidenceIds: rr(t.selectedEvidenceIds),
		unusableCandidates: i,
		truncated: t.truncated === !0,
		resolvedAt: J(e.resolvedAt),
		zeroEvidenceRequired: n.required === !0,
		zeroEvidenceReason: J(n.reasonCode),
		resolutionFingerprint: J(n.resolutionFingerprint),
		providerGenerations: {
			indexGeneration: typeof r.indexGeneration == "string" ? r.indexGeneration : null,
			rssGeneration: typeof r.rssGeneration == "string" ? r.rssGeneration : null
		},
		inputWatermark: typeof t.inputWatermark == "string" ? t.inputWatermark : null
	};
}
function gr(e) {
	return e === null ? null : typeof e == "string" ? e : void 0;
}
function _r(e) {
	if (!tr(e) || typeof e.reason != "string" || typeof e.injected != "boolean") return;
	let t = {
		policy: J(e.policy),
		requestedScope: J(e.requestedScope),
		resolvedScope: J(e.resolvedScope),
		injected: e.injected,
		reason: e.reason
	};
	if (!tr(e.ref)) return e.injected ? void 0 : t;
	let n = e.ref, r = gr(n.snapshotId), i = gr(n.asOf), a = gr(n.inputWatermark), o = gr(n.relevantEvidenceWatermark);
	if (!(r === void 0 || i === void 0 || a === void 0 || o === void 0 || typeof n.sourceKind != "string" || typeof n.scope != "string" || typeof n.status != "string" || typeof n.freshnessReason != "string" || typeof n.invalidWatermarkRows != "number" || !Number.isFinite(n.invalidWatermarkRows) || typeof n.resolvedAt != "string" || n.layer !== "source-grounded")) return {
		...t,
		ref: {
			snapshotId: r,
			sourceKind: n.sourceKind,
			scope: n.scope,
			asOf: i,
			status: n.status,
			freshnessReason: n.freshnessReason,
			inputWatermark: a,
			relevantEvidenceWatermark: o,
			invalidWatermarkRows: n.invalidWatermarkRows,
			resolvedAt: n.resolvedAt,
			layer: "source-grounded"
		}
	};
}
function vr(e) {
	return !tr(e) || typeof e.approvalId != "string" || typeof e.executedAt != "string" ? null : {
		schemaVersion: nr(e.schemaVersion),
		approvalId: e.approvalId,
		planHash: J(e.planHash),
		requestedMode: J(e.requestedMode),
		attemptedEngine: J(e.attemptedEngine),
		finalEngine: J(e.finalEngine),
		fallbackReason: e.fallbackReason === null ? null : J(e.fallbackReason),
		adapter: J(e.adapter),
		executedAt: e.executedAt
	};
}
function yr(e, t) {
	if (!tr(e)) return null;
	let n = or(t);
	if (![
		"markdown",
		"stale",
		"staleReason",
		"canonicalRevision",
		"linkedNotes",
		"counterEvidence",
		"contradictions",
		"uncertainties",
		"personalQuestions"
	].some((t) => t in e)) return null;
	let r = or(e.canonicalRevision), i = !!(n && r && (n.number !== null && r.number !== null && n.number !== r.number || n.hash && r.hash && n.hash !== r.hash)), a = Array.isArray(e.linkedNotes) ? e.linkedNotes.filter(tr).map((e) => ({
		title: J(e.title),
		type: J(e.type),
		ticker: J(e.ticker)
	})).filter((e) => e.title) : [], o = e.stale === !0 || e.staleReason === "canonical_revision_changed" || i;
	return {
		markdown: J(e.markdown),
		stale: o,
		staleReason: J(e.staleReason),
		canonicalRevision: r,
		linkedNotes: a,
		counterEvidence: rr(e.counterEvidence),
		contradictions: rr(e.contradictions),
		uncertainties: rr(e.uncertainties),
		personalQuestions: rr(e.personalQuestions),
		revisionState: o ? "stale" : r && n ? "current" : "legacy_unknown"
	};
}
function br(e, t, n) {
	return !(t in e) || e[t] === void 0 ? !1 : n === "array" ? !Array.isArray(e[t]) : !tr(e[t]);
}
function xr(e) {
	if (!tr(e) || typeof e.id != "string" || !e.id.trim() || typeof e.markdown != "string") throw Error("topic_report_contract_invalid");
	let t = [];
	for (let n of [
		"evidenceItems",
		"sourceLedger",
		"dataGaps",
		"checkpoints"
	]) br(e, n, "array") && t.push(n + "_invalid");
	for (let n of [
		"topicPlan",
		"evidencePackSummary",
		"quality",
		"researchResolution",
		"personalOverlay",
		"qualityPreflight",
		"executionProvenance",
		"marketTape",
		"marketStateResolution"
	]) br(e, n, "record") && t.push(n + "_invalid");
	let n = dr(e.evidenceItems), r = fr(e.sourceLedger), i = pr(e.dataGaps), a = lr(e.topicPlan), o = ur(e.evidencePackSummary), s = mr(e.quality), c = hr(e.researchResolution), l = _r(e.marketStateResolution), u = vr(e.executionProvenance);
	Array.isArray(e.evidenceItems) && n.length < e.evidenceItems.length && t.push("evidenceItems_rows_invalid"), Array.isArray(e.sourceLedger) && r.length < e.sourceLedger.length && t.push("sourceLedger_rows_invalid"), Array.isArray(e.dataGaps) && i.length < e.dataGaps.length && t.push("dataGaps_rows_invalid"), e.marketStateResolution !== void 0 && !l && !t.includes("marketStateResolution_invalid") && t.push("marketStateResolution_invalid"), e.executionProvenance !== void 0 && !u && !t.includes("executionProvenance_invalid") && t.push("executionProvenance_invalid");
	let d = or(e.canonicalRevision), f = yr(e.personalOverlay, d);
	for (let [n, r] of [
		["topicPlan", a],
		["evidencePackSummary", o],
		["quality", s],
		["researchResolution", c],
		["personalOverlay", f]
	]) n in e && e[n] !== void 0 && r === null && !t.includes(n + "_invalid") && t.push(n + "_invalid");
	let p = tr(e.generation) ? {
		message: J(e.generation.message),
		mode: J(e.generation.mode),
		generatedAt: J(e.generation.generatedAt)
	} : null, m = Array.isArray(e.sources) ? e.sources.filter(tr).map((e) => ({
		source: J(e.source),
		date: J(e.date),
		title: J(e.title),
		url: ir(e.url),
		path: J(e.path)
	})).filter((e) => e.title || e.source || e.url || e.path) : [];
	return {
		id: e.id,
		topicKey: J(e.topicKey),
		topicLabel: J(e.topicLabel),
		date: J(e.date),
		generatedAt: J(e.generatedAt),
		mode: J(e.mode),
		saved: e.saved === !0,
		markdown: e.markdown,
		docCount: nr(e.docCount) ?? 0,
		memoryCount: nr(e.memoryCount) ?? 0,
		userContext: typeof e.userContext == "string" || typeof e.userContext == "boolean" ? e.userContext : !1,
		generation: p,
		sources: m,
		topicPlan: a,
		evidencePackSummary: o,
		evidenceItems: n,
		sourceLedger: r,
		dataGaps: i,
		quality: s,
		researchResolution: c,
		marketStateResolution: l,
		qualityPreflight: tr(e.qualityPreflight) ? e.qualityPreflight : null,
		executionProvenance: u,
		checkpoints: Array.isArray(e.checkpoints) ? e.checkpoints.filter(tr) : [],
		marketTape: tr(e.marketTape) ? e.marketTape : null,
		canonicalRevision: d,
		personalOverlay: f,
		contractWarnings: t
	};
}
function Sr(e) {
	return Array.isArray(e) ? e.filter(tr).map((e) => ({
		id: J(e.id),
		topicKey: J(e.topicKey),
		topicLabel: J(e.topicLabel),
		date: J(e.date),
		generatedAt: J(e.generatedAt),
		mode: J(e.mode),
		saved: e.saved === !0,
		engine: J(e.engine),
		engineDetail: J(e.engineDetail)
	})).filter((e) => !!e.id) : [];
}
var Cr = {
	macro_analysis: "거시 분석",
	cross_asset_analysis: "크로스에셋 분석",
	industry_theme: "산업 테마",
	supply_chain_theme: "공급망 테마",
	policy_regulation: "정책·규제",
	geopolitical_risk: "지정학 리스크",
	earnings_theme: "실적 테마",
	factor_style: "팩터·스타일",
	company_basket: "기업군 비교",
	country_market: "국가 시장",
	portfolio_implication: "포트폴리오 영향",
	custom_research: "자유 리서치"
};
function wr(e) {
	let t = String(e || "");
	return Cr[t] || t || "유형 미상";
}
function Tr(e) {
	switch (e) {
		case "llm": return "LLM이 작성";
		case "edited": return "직접 수정함";
		case "preset": return "저장된 주제";
		default: return "규칙으로 작성";
	}
}
//#endregion
//#region src/app/changeEvents.ts
var Er = {
	added: "새로 등장",
	removed: "사라짐",
	changed: "내용 변화"
}, Dr = {
	market_driver: "시장 동인",
	issue_coverage: "이슈 보도",
	market_metric: "지표"
};
function Or(e) {
	let t = Number(e);
	return Number.isFinite(t) ? t.toLocaleString(void 0, { maximumFractionDigits: 2 }) : String(e ?? "");
}
function kr(e) {
	let t = e || {}, n = Number(t.rank), r = Number(t.share), i = [];
	return Number.isFinite(n) && n > 0 && i.push(`${n}순위`), Number.isFinite(r) && r > 0 && i.push(`비중 ${Math.round(r * 100)}%`), i.join(" · ");
}
function Ar(e, t) {
	if (t == null) return "";
	if (e.kind === "market_metric" || typeof t != "object") return Or(t);
	let n = kr(t);
	if (n) return n;
	let r = t, i = [];
	return r.market && i.push(String(r.market)), r.impact && i.push(String(r.impact)), !i.length && Number(r.docCount) > 0 && i.push(`기사 ${Number(r.docCount)}건`), i.join(" · ");
}
function jr(e) {
	let t = e.currentValue || {}, n = e.previousValue || {}, r = Number(t.rank), i = Number(n.rank), a = Number(t.share), o = [];
	return Number.isFinite(r) && r > 0 && o.push(Number.isFinite(i) && i > 0 && i !== r ? `${i}순위 → ${r}순위` : `${r}순위`), Number.isFinite(a) && a > 0 && o.push(`비중 ${Math.round(a * 100)}%`), o.join(" · ");
}
function Mr(e) {
	let t = e.currentValue;
	if (e.kind === "market_metric") return e.previousValue != null && t != null ? `${Or(e.previousValue)} → ${Or(t)}` : t == null ? "" : Or(t);
	if (e.kind === "market_driver") return jr(e);
	if (t && typeof t == "object") {
		let e = t, n = [];
		return Array.isArray(e.markets) && e.markets.length ? n.push(e.markets.join(", ")) : e.market && n.push(String(e.market)), Number(e.docCount) > 0 && n.push(`기사 ${Number(e.docCount)}건`), e.impact && n.push(String(e.impact)), n.join(" · ");
	}
	return "";
}
function Nr(e) {
	let t = e.changedItems || [];
	if (!t.length) return "";
	let n = t[0], r = Er[String(n.change || "")] || "변화", i = Dr[String(n.kind || "")], a = i ? `${i} ${r}` : r, o = t.length > 1 ? `외 ${t.length - 1}건` : "";
	return [
		a,
		Mr(n),
		o
	].filter(Boolean).join(" · ");
}
var Pr = {
	briefing: "브리핑",
	company_analysis: "기업 분석",
	topic_report: "딥 리서치",
	market_memory: "시장 내러티브"
}, Fr = [
	"us",
	"kr",
	"europe",
	"jp"
];
f.us, f.kr, f.europe, f.jp;
function Ir(e) {
	let t = e.previousSessionCount || 0;
	if (!t) return "비교 기준 없음";
	if (t === 1) return "직전 거래일 대비";
	let n = e.previousCollectedCount;
	return `직전 ${t}거래일 합산${typeof n == "number" ? ` ${n}건` : ""} 대비`;
}
var Lr = [
	"blue",
	"teal",
	"gold",
	"purple"
];
function Rr(e, t) {
	return e.isOther ? "other" : Lr[t] || "other";
}
function zr(e) {
	let t = e.deltaPp;
	return t == null || !Number.isFinite(t) ? {
		text: "",
		tone: "flat"
	} : Math.abs(t) < 1 ? {
		text: "─",
		tone: "flat"
	} : t > 0 ? {
		text: `▲ +${Math.round(t)}%p`,
		tone: "up"
	} : {
		text: `▼ ${Math.round(t)}%p`,
		tone: "down"
	};
}
function Br({ market: e }) {
	let [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)("");
	if ((0, l.useEffect)(() => {
		let t = !0;
		return i(""), B(`/api/dashboard/story-share?market=${e}`).then((e) => {
			t && n(e);
		}).catch((e) => {
			t && i(e instanceof Error ? e.message : "이야기 비중을 불러오지 못했습니다.");
		}), () => {
			t = !1;
		};
	}, [e]), r) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "story-share__note",
		children: r
	});
	if (!t) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "story-share__note",
		children: "이야기 비중을 계산하는 중입니다."
	});
	let a = t.items || [];
	return a.length ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "story-share",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "story-share__head",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					className: "story-share__title",
					children: "오늘의 이야기 비중"
				}), /* @__PURE__ */ (0, K.jsxs)("span", {
					className: "story-share__meta",
					children: [
						"수집 기사 ",
						t.collectedCount || 0,
						"건 · ",
						Ir(t)
					]
				})]
			}),
			t.smallSample && /* @__PURE__ */ (0, K.jsxs)("p", {
				className: "story-share__note",
				children: [
					"수집량이 적어(",
					t.collectedCount || 0,
					"건) 비중과 증감이 크게 흔들릴 수 있습니다."
				]
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "story-share__bar",
				role: "img",
				"aria-label": `이야기 비중: ${a.map((e) => `${e.label} ${Math.round(e.share * 100)}%`).join(", ")}`,
				children: a.map((e, t) => /* @__PURE__ */ (0, K.jsx)("span", {
					"data-tone": Rr(e, t),
					style: { width: `${Math.max(e.share * 100, 1)}%` }
				}, e.label))
			}),
			/* @__PURE__ */ (0, K.jsx)("ul", {
				className: "story-share__legend",
				children: a.map((e, t) => {
					let n = zr(e);
					return /* @__PURE__ */ (0, K.jsxs)("li", {
						"data-other": e.isOther ? "true" : void 0,
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "story-share__dot",
								"data-tone": Rr(e, t),
								"aria-hidden": "true"
							}),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "story-share__label",
								children: e.label
							}),
							/* @__PURE__ */ (0, K.jsxs)("span", {
								className: "story-share__count",
								children: [e.count, "건"]
							}),
							/* @__PURE__ */ (0, K.jsxs)("span", {
								className: "story-share__share",
								children: [Math.round(e.share * 100), "%"]
							}),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "story-share__delta",
								"data-tone": n.tone,
								children: e.isOther ? "" : n.text
							})
						]
					}, e.label);
				})
			}),
			/* @__PURE__ */ (0, K.jsxs)("p", {
				className: "story-share__note",
				children: ["수집된 뉴스 기준 규칙 계산 · 브리핑과 독립 · 비중 이동은 보도량 변화일 뿐 내용 변화가 아닙니다", t.driverBasis?.count ? ` · 고정된 ${t.driverBasis.count}개 동인 기준` : ""]
			})
		]
	}) : /* @__PURE__ */ (0, K.jsx)("p", {
		className: "story-share__note",
		children: "이 날짜에 수집된 시장 뉴스가 없습니다. RSS 수집 후 다시 확인해 주세요."
	});
}
//#endregion
//#region src/app/dashboard/ChangeFeed.tsx
var Vr = {
	major_change: "중대한 변화",
	developing_signal: "발전 중",
	conflicting_uncertain: "충돌·불확실",
	no_material_change: "중대한 변화 없음",
	baseline_created: "기준선 생성",
	insufficient_basis: "근거 부족"
}, Hr = {
	new_information: {
		label: "새 정보",
		tone: "burgundy"
	},
	reversal: {
		label: "방향 전환",
		tone: "gold"
	},
	trend_development: {
		label: "흐름 진전",
		tone: "blue"
	},
	coverage_shift_only: {
		label: "보도량 이동",
		tone: "muted"
	},
	no_new_information: {
		label: "변화 없음",
		tone: "muted"
	},
	not_evaluated: {
		label: "내용 미평가",
		tone: "muted"
	}
}, Ur = [
	"new_information",
	"reversal",
	"trend_development",
	"coverage_shift_only",
	"no_new_information",
	"not_evaluated"
];
function Wr(e) {
	let t = String(e.artifactKind || ""), n = String(e.artifactId || "");
	if (t === "briefing") {
		let t = n.slice(0, 10);
		return /^\d{4}-\d{2}-\d{2}$/.test(t) ? `#/briefing/${t}/${Yr(n, e.lineageId)}/${qr(n, e.lineageId)}` : "#/briefing";
	}
	return t === "company_analysis" ? "#/analysis" : t === "topic_report" ? "#/deep-research" : t === "market_memory" ? "#/market-memory" : "#/dashboard";
}
var Gr = [
	"us",
	"kr",
	"europe",
	"jp"
], Kr = ["weekly"];
function qr(e, t) {
	return Kr.find((t) => e.endsWith(`.${t}`)) || RegExp(`^briefing:[a-z]+:(${Kr.join("|")})$`).exec(String(t || ""))?.[1] || "daily";
}
function Jr(e) {
	let t = Kr.find((t) => e.endsWith(`.${t}`));
	return t ? e.slice(0, -t.length - 1) : e;
}
function Yr(e, t) {
	let n = Jr(e);
	return Gr.find((e) => n.endsWith(`.${e}`)) || RegExp(`^briefing:(${Gr.join("|")})(?::[a-z]+)?$`).exec(String(t || ""))?.[1] || "both";
}
function Xr(e) {
	let t = e.changedItems || [];
	for (let e of Ur) {
		let n = t.find((t) => t.semanticVerdict === e);
		if (n) return n;
	}
	return t[0];
}
function Zr(e) {
	let t = Xr(e), n = [`${Pr[e.artifactKind || ""] || "보고서"} 변화에 대해 물어볼게. 주제: ${t?.subject || "변화 항목"}`], r = t ? Ar(t, t.previousValue) : "", i = t ? Ar(t, t.currentValue) : "";
	(r || i) && n.push(`변화: ${r || "기준 없음"} → ${i || "현재 없음"}`);
	let a = Hr[String(t?.semanticVerdict || "")];
	a && n.push(`의미 분류: ${a.label}`), t?.semanticNote && n.push(`분류 근거: ${t.semanticNote}`);
	let o = [...(t?.previousContextDocs || []).map((e) => `직전: ${e}`), ...(t?.contextDocs || []).map((e) => `현재: ${e}`)];
	return o.length && n.push(`대표 기사:\n${o.map((e) => `- ${e}`).join("\n")}`), e.baselineRef?.id && n.push(`비교 기준: ${e.baselineRef.id}`), n.push("이 변화가 실제로 얼마나 중요한지, 투자 관점에서 무엇을 확인해야 하는지 설명해줘."), n.join("\n");
}
function Qr(e) {
	return Pr[e.artifactKind || ""] || e.artifactKind || "보고서";
}
function $r(e) {
	return `${e.artifactKind}-${e.artifactId}-${e.generatedAt}`;
}
function ei({ event: e }) {
	(0, l.useEffect)(() => {
		yn().applyAgentBranding?.();
	}, []);
	let t = Xr(e), n = Hr[String(t?.semanticVerdict || "")], r = t?.semanticNote || Nr(e);
	return /* @__PURE__ */ (0, K.jsx)("li", {
		"data-status": e.status,
		"data-tone": n?.tone || "",
		children: /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "cockpit-change-card",
			children: [
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "cockpit-change-card__meta",
					children: [
						/* @__PURE__ */ (0, K.jsx)("span", {
							className: "chip status-chip",
							children: Vr[e.status || ""] || e.status
						}),
						n ? /* @__PURE__ */ (0, K.jsx)("span", {
							className: "chip change-verdict-chip",
							"data-tone": n.tone,
							children: n.label
						}) : null,
						/* @__PURE__ */ (0, K.jsx)("time", { children: e.generatedAt ? new Date(e.generatedAt).toLocaleString("ko-KR") : "" })
					]
				}),
				/* @__PURE__ */ (0, K.jsx)("strong", { children: t?.subject || Qr(e) }),
				r ? /* @__PURE__ */ (0, K.jsx)("em", {
					className: "cockpit-change-reason",
					children: r
				}) : null,
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "cockpit-change-card__actions",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "btn btn--sm",
						onClick: () => {
							window.location.hash = Wr(e);
						},
						children: "보고서 열기"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "btn btn--icon agent-action agent-ask-btn",
						"data-tooltip": "Agent에게 묻기",
						"data-tooltip-pos": "left",
						"aria-label": "Agent에게 묻기",
						onClick: () => nt({ message: Zr(e) }),
						children: /* @__PURE__ */ (0, K.jsx)("span", {
							className: "agent-logo-slot",
							"aria-hidden": "true"
						})
					})]
				})
			]
		})
	});
}
var ti = /* @__PURE__ */ new Set([
	"new_information",
	"reversal",
	"trend_development"
]), ni = /* @__PURE__ */ new Set([
	...ti,
	"coverage_shift_only",
	"no_new_information"
]), ri = /* @__PURE__ */ new Set(["briefing"]);
function ii(e) {
	return (e.changedItems || []).some((e) => String(e.semanticVerdict || "") === "not_evaluated");
}
var ai = /* @__PURE__ */ new Set(["llm_unavailable", "generation_rules_mode"]);
function oi(e) {
	return e.some((e) => ai.has(String(e.semanticEvaluation?.reason || "")));
}
function si(e) {
	let t = [], n = 0;
	for (let r of e) {
		let e = String(Xr(r)?.semanticVerdict || "");
		if (ti.has(e)) {
			t.push(r);
			continue;
		}
		ni.has(e) || ri.has(String(r.artifactKind || "")) && ii(r) && (n += 1);
	}
	return {
		confirmed: t,
		unjudged: n
	};
}
function ci(e, t) {
	return e <= 0 ? "아직 확인된 내용 변화가 없습니다." : t ? `내용 변화를 판정하지 못한 기록이 ${e}건 있습니다. 설정에서 AI를 연결하면 무엇이 달라졌는지 읽어 줍니다.` : `내용 변화를 아직 판정하지 못한 기록이 ${e}건 있습니다. 다음 브리핑 생성에서 함께 판정합니다.`;
}
function li({ events: e }) {
	let [t, n] = (0, l.useState)("us"), { confirmed: r, unjudged: i } = si(e), a = oi(e);
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "cockpit-panel cockpit-change-feed",
		"aria-labelledby": "cockpit-change-title",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cockpit-panel__head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "CHANGE INTELLIGENCE" }), /* @__PURE__ */ (0, K.jsx)("h2", {
					id: "cockpit-change-title",
					children: "무엇이 달라졌나"
				})] }), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "segment story-share__toggle",
					role: "group",
					"aria-label": "이야기 비중 시장",
					children: Fr.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						"aria-pressed": t === e,
						onClick: () => n(e),
						children: d[e]
					}, e))
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)(Br, { market: t }),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cockpit-change-feed__subhead",
				children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "내용의 변화" }), /* @__PURE__ */ (0, K.jsxs)("b", { children: [r.length, "건"] })]
			}),
			r.length ? /* @__PURE__ */ (0, K.jsx)("ol", { children: r.map((e) => /* @__PURE__ */ (0, K.jsx)(ei, { event: e }, $r(e))) }) : /* @__PURE__ */ (0, K.jsx)("p", {
				className: "cockpit-empty",
				children: ci(i, a)
			})
		]
	});
}
//#endregion
//#region src/app/briefing/BriefingChangeStrip.tsx
function ui({ summary: e }) {
	if (!e || !e.status) return null;
	let t = (e.changedItems || []).filter((e) => e.semanticVerdict || e.semanticNote || e.subject);
	if (!t.length || ["baseline_created", "insufficient_basis"].includes(String(e.status))) return null;
	let n = t.filter((e) => [
		"new_information",
		"reversal",
		"trend_development"
	].includes(String(e.semanticVerdict || ""))).slice(0, 3), r = n.length ? n : t.slice(0, 1), i = e.baselineRef?.id ? `${e.baselineRef.id} 대비` : "";
	return /* @__PURE__ */ (0, K.jsxs)("aside", {
		className: "briefing-change-strip",
		"data-status": e.status,
		"aria-label": "이 브리핑에서 달라진 것",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "briefing-change-strip__head",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "chip status-chip",
						children: Vr[e.status] || e.status
					}),
					/* @__PURE__ */ (0, K.jsx)("strong", { children: "이 브리핑에서 달라진 것" }),
					i ? /* @__PURE__ */ (0, K.jsx)("em", { children: i }) : null
				]
			}),
			/* @__PURE__ */ (0, K.jsx)("ul", { children: r.map((e) => {
				let t = Hr[String(e.semanticVerdict || "")];
				return /* @__PURE__ */ (0, K.jsxs)("li", { children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "briefing-change-strip__subject",
						children: e.subject
					}),
					t ? /* @__PURE__ */ (0, K.jsx)("span", {
						className: "chip change-verdict-chip",
						"data-tone": t.tone,
						children: t.label
					}) : null,
					e.semanticNote ? /* @__PURE__ */ (0, K.jsx)("span", {
						className: "briefing-change-strip__note",
						children: e.semanticNote
					}) : null
				] }, e.id || e.subject);
			}) }),
			n.length ? null : /* @__PURE__ */ (0, K.jsx)("p", {
				className: "briefing-change-strip__fallback",
				children: Nr(e)
			})
		]
	});
}
//#endregion
//#region src/app/BriefingRoute.tsx
var di = [
	"us",
	"kr",
	"europe",
	"jp"
], fi = {
	us: d.us,
	kr: d.kr,
	europe: d.europe,
	jp: d.jp
};
function pi(e) {
	return e.length === 1 ? e[0] : e.length === di.length ? "all" : e.length === 2 && e.includes("us") && e.includes("kr") ? "both" : "multi";
}
var mi = [
	...di,
	"all",
	"both",
	"multi"
], hi = {
	us: "미국",
	kr: "한국",
	europe: "유럽",
	jp: "일본",
	all: "통합",
	both: "통합",
	multi: "선택 시장"
}, gi = {
	us: "US",
	kr: "KR",
	europe: "EU",
	jp: "JP",
	all: "ALL",
	both: "US/KR",
	multi: "MULTI"
}, _i = /* @__PURE__ */ new Set([
	"미국장",
	"한국장",
	"유럽장",
	"일본장",
	"종합",
	"선택 시장"
]), vi = {
	default: "기본",
	market_focused: "시황 중심",
	concise: "요약"
}, yi = {
	daily: "일간",
	weekly: "주간 요약"
}, bi = 20;
function xi(e) {
	return String(e || "").replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1.$2.$3");
}
function Si(e) {
	let t = String(e || "").match(/^(\d{4})-(\d{2})/);
	return t ? `${t[1]}.${t[2]}` : "월 미상";
}
function Ci() {
	let e = /* @__PURE__ */ new Date(), t = e.getTimezoneOffset() * 6e4;
	return new Date(e.getTime() - t).toISOString().slice(0, 10);
}
function wi(e) {
	return String(e || "").replace(/\s+[—–-]\s+\d{4}[.-]\d{2}[.-]\d{2}\s*$/, "").trim();
}
function Ti(e) {
	let t = Pi(e), n = Fi(e), r = Ii(e), i = n === "us" ? "US Market Briefing" : n === "kr" ? "KR Market Briefing" : wi(e.title || "Daily Market Briefing"), a = xi(t), o = e.title || (a ? `${i} — ${a}` : i), s = (e.tags || []).filter((e) => !_i.has(String(e || "").trim())), c = a ? `${mn(e.reportDate || e.date)} KST 발행` : "발행일 미상";
	return {
		date: t,
		scope: n,
		kind: r,
		title: o,
		chips: s,
		engine: e.engine || "",
		engineDetail: e.engineDetail || "",
		foot: c
	};
}
function Ei(e) {
	return new Promise((t) => window.setTimeout(t, e));
}
function Di(e) {
	return mi.includes(e) ? e : "both";
}
function Oi(e) {
	return e === "weekly" ? "weekly" : "daily";
}
function ki(e, t) {
	let n = Di(e);
	return di.includes(n) ? n : t[0] ?? n;
}
function Ai() {
	let e = window.location.hash.match(/^#\/?briefing\/(\d{4}-\d{2}-\d{2})(?:\/(us|kr|europe|jp|all|both|multi))?(?:\/(daily|weekly))?$/);
	return e ? {
		date: e[1],
		scope: Di(e[2]),
		kind: Oi(e[3])
	} : null;
}
function ji() {
	return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "briefing";
}
function Mi(e, t = "both", n = "daily") {
	window.location.hash = e ? `#/briefing/${e}/${t}/${n}` : "#/briefing";
}
function Ni(e = "", t = "시장 브리핑") {
	let n = e.replace(/\r\n/g, "\n").split("\n"), r = n.findIndex((e) => e.trim());
	if (r < 0) return {
		title: t,
		body: ""
	};
	let i = n[r].trim().match(/^#\s+(.+)$/);
	return i ? {
		title: i[1],
		body: n.slice(r + 1).join("\n").trim()
	} : {
		title: t,
		body: e
	};
}
function Pi(e) {
	return e.reportDate || e.date || "";
}
function Fi(e) {
	return Di(e.marketScope || e.scope);
}
function Ii(e) {
	return Oi(e.kind);
}
function Li(e, t, n) {
	return !t && !n || [Pi(e), e.sessionDate || ""].filter(Boolean).some((e) => (!t || e >= t) && (!n || e <= n));
}
function Ri(e, t) {
	let n = String(t || e || "note"), r = 2166136261;
	for (let e = 0; e < n.length; e += 1) r ^= n.charCodeAt(e), r = Math.imul(r, 16777619) >>> 0;
	return `${e}-${r.toString(36)}`;
}
function zi(e, t) {
	return {
		id: Ri("brief", `${e}:${t}`),
		noteType: "market_memo",
		title: e ? `브리핑 ${e} 투자 노트` : "브리핑 투자 노트",
		label: e ? `브리핑 ${e}` : "브리핑",
		topic: t,
		reportKind: "briefing",
		reportId: e,
		linkedReports: [e ? `Daily Market Briefing — ${e}` : ""].filter(Boolean)
	};
}
function Bi(e) {
	let t = e;
	return !!(t?.id && I(t.status));
}
function Vi(e) {
	let t = e?.jobs;
	return Array.isArray(t) && t.every(Bi) ? t : null;
}
function Hi(e) {
	let t = e?.reports;
	return Array.isArray(t) && t.length > 0 ? t : null;
}
async function Ui(e) {
	let t = e;
	for (; I(t.status);) await Ei(1e3), t = await B(`/api/jobs/${encodeURIComponent(t.id)}`);
	if (t.status !== "done") throw Error(t.message || t.error || "브리핑 생성에 실패했습니다.");
	return t;
}
function Wi() {
	let e = fn("briefing"), [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)(() => Ai()), [a, o] = (0, l.useState)(null), [s, c] = (0, l.useState)(!1), [u, d] = (0, l.useState)(!1), [f, p] = (0, l.useState)(""), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(""), [v, y] = (0, l.useState)(["us"]), { isSelected: b } = vn(), x = di.filter((e) => b(e)), S = pi(v);
	function C(e) {
		y((t) => {
			let n = t.includes(e) ? t.filter((t) => t !== e) : [...t, e];
			return n.length ? di.filter((e) => n.includes(e)) : t;
		});
	}
	let [w, T] = (0, l.useState)("default"), [E, D] = (0, l.useState)("daily"), [O, k] = (0, l.useState)(() => Ci()), [A, j] = (0, l.useState)(""), [M, N] = (0, l.useState)("all"), [P, F] = (0, l.useState)("all"), [I, L] = (0, l.useState)("all"), [R, z] = (0, l.useState)(""), [H, U] = (0, l.useState)(""), [ee, te] = (0, l.useState)("recent"), [W, G] = (0, l.useState)(0), q = (0, l.useCallback)(async () => {
		c(!0), p("");
		try {
			let e = await B(`/api/briefings/index?${new URLSearchParams({
				offset: "0",
				limit: "100",
				q: A,
				marketScope: M,
				briefingType: P,
				kind: I,
				dateFrom: R,
				dateTo: H
			})}`);
			n(e), Qe("briefing", {
				surface: "briefing",
				viewId: "briefing",
				reportKind: "",
				reportId: ""
			});
		} catch (e) {
			p(e instanceof Error ? e.message : "브리핑 목록을 불러오지 못했습니다.");
		} finally {
			c(!1);
		}
	}, [
		H,
		I,
		M,
		A,
		R,
		P
	]);
	(0, l.useEffect)(() => {
		q();
	}, [q, e]), (0, l.useEffect)(() => {
		let e = () => {
			ji() && i(Ai());
		};
		return window.addEventListener("hashchange", e), e(), () => window.removeEventListener("hashchange", e);
	}, []), (0, l.useEffect)(() => {
		let e = (e) => {
			let t = e.detail;
			Re(t, window.FolioAgent?.currentContext) && G((e) => e + 1);
		};
		return window.addEventListener(se, e), () => window.removeEventListener(se, e);
	}, []), (0, l.useEffect)(() => {
		let e = !0;
		async function t(t, n, r) {
			c(!0), p("");
			try {
				let i = await B(`/api/briefings/${encodeURIComponent(t)}?includePersonal=true&marketScope=${encodeURIComponent(n)}&kind=${encodeURIComponent(r)}`);
				if (!e) return;
				o(i), Qe("briefing", {
					surface: "briefing_reader",
					viewId: "briefing",
					reportKind: "briefing",
					reportId: t,
					marketScope: n
				});
			} catch (t) {
				if (!e) return;
				o(null), p(t instanceof Error ? t.message : "브리핑을 불러오지 못했습니다.");
			} finally {
				e && c(!1);
			}
		}
		return r ? t(r.date, r.scope, r.kind) : (o(null), Qe("briefing", {
			surface: "briefing",
			viewId: "briefing",
			reportKind: "",
			reportId: ""
		})), () => {
			e = !1;
		};
	}, [r, W]);
	async function ne(e) {
		let t = a?.date || r?.date || "", n = Di(a?.marketScope || r?.scope), i = Oi(a?.kind || r?.kind);
		if (t) {
			_(e), h(e === "notion" ? "Notion에 내보내는 중..." : "Obsidian에 내보내는 중...");
			try {
				let r = `marketScope=${encodeURIComponent(n)}&kind=${encodeURIComponent(i)}`, a = e === "notion" ? await V(`/api/briefings/${encodeURIComponent(t)}/export-notion?${r}`, {
					marketScope: n,
					kind: i
				}) : await V(`/api/briefings/${encodeURIComponent(t)}/export-obsidian?${r}`, {
					marketScope: n,
					kind: i
				});
				h(e === "notion" ? a.notionUrl ? `Notion 내보냄: ${a.title || a.notionUrl}` : "Notion에 내보냈습니다." : `Obsidian 내보냄: ${a.filename || t}`);
			} catch (e) {
				h(e instanceof Error ? e.message : "내보내기에 실패했습니다.");
			} finally {
				_("");
			}
		}
	}
	async function re() {
		let e = a?.date || r?.date || "", t = Di(a?.marketScope || r?.scope), n = Oi(a?.kind || r?.kind);
		if (e) {
			_("overlay"), h("개인 해석을 생성하는 중...");
			try {
				let r = `marketScope=${encodeURIComponent(t)}&kind=${encodeURIComponent(n)}`, i = await V(`/api/briefings/${encodeURIComponent(e)}/personal-overlay?${r}`, {
					marketScope: t,
					kind: n
				});
				Bi(i) && await Ui(i);
				let a = await B(`/api/briefings/${encodeURIComponent(e)}?includePersonal=true&${r}`);
				o(a), h("개인 해석을 생성했습니다.");
			} catch (e) {
				h(e instanceof Error ? e.message : "개인 해석 생성에 실패했습니다.");
			} finally {
				_("");
			}
		}
	}
	async function ie(e, t, n = "daily") {
		if (e && window.confirm(`${e} ${hi[t]} ${yi[n]} 브리핑을 삭제할까요?`)) {
			_(`delete-${e}-${t}-${n}`);
			try {
				let r = t === "both" || t === "all" || t === "multi", i = new URLSearchParams({ kind: n });
				r || i.set("market", t);
				let a = `?${i}`, o = await fetch(`/api/briefings/${encodeURIComponent(e)}${a}`, { method: "DELETE" });
				if (!o.ok) throw Error(o.status === 404 ? "삭제할 브리핑을 찾지 못했습니다." : "브리핑 삭제에 실패했습니다.");
				await q();
			} catch (e) {
				p(e instanceof Error ? e.message : "브리핑 삭제에 실패했습니다.");
			} finally {
				_("");
			}
		}
	}
	async function ae(e) {
		d(!0), p("");
		try {
			let t = await V("/api/briefings", {
				date: e || void 0,
				strictDate: !!e,
				markets: v,
				briefingType: w,
				kind: E
			}), n = Vi(t);
			if (n) {
				let e = await Promise.all(n.map(Ui));
				await q();
				let t = e[0]?.result?.date || e[0]?.result?.artifactId || "";
				t && Mi(t, ki(S, v), E);
				return;
			}
			if (Bi(t)) {
				let n = await Ui(t), r = n.result?.date || n.result?.artifactId || e || "";
				await q(), r && Mi(r, ki(S, v), E);
				return;
			}
			let r = Hi(t);
			if (r) {
				await q();
				let e = r[0];
				e?.date && Mi(e.date, ki(e.marketScope || S, v), E);
				return;
			}
			let i = t.date || e || "";
			await q(), i && Mi(i, ki(t.marketScope || S, v), E);
		} catch (e) {
			p(e instanceof Error ? e.message : "브리핑 생성에 실패했습니다.");
		} finally {
			d(!1);
		}
	}
	let oe = t?.items || [], ce = (0, l.useMemo)(() => oe.filter((e) => {
		let t = Fi(e), n = e.briefingType || "default";
		if (M === "aggregate") {
			if (t !== "all" && t !== "both" && t !== "multi") return !1;
		} else if (M !== "all" && t !== M) return !1;
		return P !== "all" && n !== P || I !== "all" && Ii(e) !== I ? !1 : Li(e, R, H);
	}), [
		H,
		I,
		M,
		R,
		P,
		oe
	]), le = (0, l.useMemo)(() => {
		let e = [...ce].sort((e, t) => String(Pi(t) || t.generatedAt || "").localeCompare(String(Pi(e) || e.generatedAt || "")));
		if (ee === "recent") return e.length ? [{
			label: "최근 브리핑",
			rows: e.slice(0, bi)
		}] : [];
		if (ee === "month") {
			let t = /* @__PURE__ */ new Map();
			for (let n of e) {
				let e = Si(Pi(n));
				t.has(e) || t.set(e, []), t.get(e)?.push(n);
			}
			return Array.from(t.entries()).map(([e, t]) => ({
				label: e,
				rows: t
			}));
		}
		return [
			"us",
			"kr",
			"europe",
			"jp",
			"both"
		].map((t) => ({
			label: `${hi[t]} 시장`,
			rows: e.filter((e) => Fi(e) === t)
		})).filter((e) => e.rows.length > 0);
	}, [ee, ce]), ue = (0, l.useMemo)(() => Ni(a?.markdown || "", a?.title || "시장 브리핑"), [a?.markdown, a?.title]), de = a?.title || ue.title, fe = a?.publicationDate || a?.date || r?.date || "";
	return r && a ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-briefing-route",
		"data-briefing-route": !0,
		children: [f && /* @__PURE__ */ (0, K.jsx)("p", {
			className: "react-dashboard-error",
			children: f
		}), /* @__PURE__ */ (0, K.jsxs)(Yn, {
			eyebrow: r.kind === "weekly" ? "WEEKLY BRIEFING" : "DAILY BRIEFING",
			title: de,
			meta: `${xi(fe)} KST 발행`,
			agentContext: {
				surface: "briefing_reader",
				viewId: "briefing",
				reportKind: "briefing",
				reportId: a.date || r.date,
				marketScope: Di(a.marketScope || r.scope)
			},
			breadcrumb: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
				type: "button",
				onClick: () => Mi(),
				children: "브리핑"
			}), /* @__PURE__ */ (0, K.jsx)("span", { children: de })] }),
			onClose: () => Mi(),
			actionSlot: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
				/* @__PURE__ */ (0, K.jsx)(bn, {
					title: "AI",
					children: /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "agent",
						onClick: () => nt({
							surface: "briefing_reader",
							reportKind: "briefing",
							reportId: a.date || r.date,
							marketScope: Di(a.marketScope || r.scope),
							message: `${de}의 핵심과 투자 판단 체크포인트를 요약해줘.`,
							autoSubmit: !0
						}),
						children: "Agent에게 묻기"
					})
				}),
				/* @__PURE__ */ (0, K.jsx)(bn, {
					title: "노트",
					children: /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "link",
						disabled: g === "overlay",
						onClick: re,
						children: g === "overlay" ? "생성 중" : "내 노트와 연결"
					})
				}),
				/* @__PURE__ */ (0, K.jsxs)(bn, {
					title: "내보내기",
					children: [/* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "notion",
						disabled: g === "notion",
						onClick: () => ne("notion"),
						children: g === "notion" ? "내보내는 중" : "Notion으로 내보내기"
					}), /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "obsidian",
						disabled: g === "obsidian",
						onClick: () => ne("obsidian"),
						children: g === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"
					})]
				}),
				m && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "react-reader-status",
					children: m
				})
			] }),
			noteIdentity: zi(a.date || r.date, Di(a.marketScope || r.scope)),
			noteLinkedTitle: de,
			noteOverlay: yr(a.personalOverlay, a.canonicalRevision),
			children: [/* @__PURE__ */ (0, K.jsx)(ui, { summary: a.changeSummary }), /* @__PURE__ */ (0, K.jsx)(On, {
				markdown: ue.body || a.markdown || "",
				marketScope: Di(a.marketScope || r.scope),
				briefing: a,
				sourcePanelHtml: yn().briefingSourcePanelHtml?.(a) || ""
			})]
		})]
	}) : /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-briefing-route",
		"data-briefing-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Briefing",
				title: "브리핑",
				description: "수집된 최신 뉴스와 시장 데이터로 미국·한국·유럽·일본장 흐름을 요약합니다.",
				actions: /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: q,
					disabled: s,
					children: s ? "불러오는 중" : "새로고침"
				})
			}),
			/* @__PURE__ */ (0, K.jsx)("section", {
				className: "brief-gen-box input-panel react-briefing-generation",
				"aria-label": "브리핑 생성",
				children: /* @__PURE__ */ (0, K.jsxs)("section", {
					className: "brief-gen-panel brief-gen-settings",
					children: [
						/* @__PURE__ */ (0, K.jsx)("div", {
							className: "brief-gen-panel-head",
							children: /* @__PURE__ */ (0, K.jsx)("h3", { children: "브리핑 설정" })
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "brief-gen-settings-row",
							children: [
								/* @__PURE__ */ (0, K.jsx)("div", {
									className: "brief-gen-field brief-gen-market-field",
									children: /* @__PURE__ */ (0, K.jsxs)("div", {
										className: "brief-market-segment",
										role: "group",
										"aria-label": "생성할 시장",
										"data-scope": S,
										children: [/* @__PURE__ */ (0, K.jsx)("span", {
											className: "brief-market-segment-title",
											children: "시장"
										}), (x.length ? x : di).map((e) => /* @__PURE__ */ (0, K.jsxs)("label", { children: [/* @__PURE__ */ (0, K.jsx)("input", {
											type: "checkbox",
											name: "reactBriefingMarkets",
											value: e,
											checked: v.includes(e),
											onChange: () => C(e)
										}), /* @__PURE__ */ (0, K.jsx)("span", { children: fi[e] })] }, e))]
									})
								}),
								/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "gen-option quality-option",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "종류" }), /* @__PURE__ */ (0, K.jsx)("select", {
										value: E,
										onChange: (e) => D(e.currentTarget.value),
										children: Object.entries(yi).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
											value: e,
											children: t
										}, e))
									})]
								}),
								E === "daily" && /* @__PURE__ */ (0, K.jsxs)("label", {
									className: "gen-option quality-option",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "유형" }), /* @__PURE__ */ (0, K.jsx)("select", {
										value: w,
										onChange: (e) => T(e.currentTarget.value),
										children: Object.entries(vi).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
											value: e,
											children: t
										}, e))
									})]
								})
							]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "brief-gen-actionbar",
							children: [
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn btn--primary",
									type: "button",
									onClick: () => ae(),
									disabled: u,
									children: u ? "생성 중" : E === "weekly" ? "이번 주 요약 생성" : "오늘 브리핑 생성"
								}),
								/* @__PURE__ */ (0, K.jsx)("span", {
									className: "brief-gen-alt",
									children: "또는"
								}),
								/* @__PURE__ */ (0, K.jsx)("input", {
									type: "date",
									value: O,
									onChange: (e) => k(e.currentTarget.value),
									"aria-label": E === "weekly" ? "주간 발행일" : `${hi[S]} 기준일`,
									title: E === "weekly" ? "이 날짜까지의 지난 7일을 요약하고 다음주 일정을 붙입니다" : `${hi[S]} 세션 기준일`
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									onClick: () => ae(O),
									disabled: u || !O,
									children: E === "weekly" ? "이 날짜까지 요약" : "이 기준일로 생성"
								})
							]
						})
					]
				})
			}),
			f && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: f
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "find-bar",
				"aria-label": "저장 브리핑 검색",
				children: [
					/* @__PURE__ */ (0, K.jsx)("input", {
						className: "find-bar__search",
						type: "search",
						value: A,
						onChange: (e) => j(e.currentTarget.value),
						placeholder: "제목·요약·본문 검색",
						"aria-label": "저장 브리핑 검색"
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "브리핑 시장",
							value: M,
							onChange: (e) => N(e.currentTarget.value),
							children: [
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "all",
									children: "전체"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "us",
									children: "미국장"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "kr",
									children: "한국장"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "europe",
									children: "유럽장"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "jp",
									children: "일본장"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "aggregate",
									children: "종합 보고서"
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "종류" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "브리핑 종류",
							value: I,
							onChange: (e) => L(e.currentTarget.value),
							children: [/* @__PURE__ */ (0, K.jsx)("option", {
								value: "all",
								children: "전체"
							}), Object.entries(yi).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
								value: e,
								children: t
							}, e))]
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "유형" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "브리핑 유형",
							value: P,
							onChange: (e) => F(e.currentTarget.value),
							children: [/* @__PURE__ */ (0, K.jsx)("option", {
								value: "all",
								children: "전체"
							}), Object.entries(vi).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
								value: e,
								children: t
							}, e))]
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", { children: "기간" }),
							/* @__PURE__ */ (0, K.jsx)("input", {
								type: "date",
								"aria-label": "시작일",
								value: R,
								onChange: (e) => z(e.currentTarget.value)
							}),
							/* @__PURE__ */ (0, K.jsx)("input", {
								type: "date",
								"aria-label": "종료일",
								value: H,
								onChange: (e) => U(e.currentTarget.value)
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "보기" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "브리핑 보기 방식",
							value: ee,
							onChange: (e) => te(e.currentTarget.value),
							children: [
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "recent",
									children: "최근"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "month",
									children: "월별"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "market",
									children: "시장별"
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--text find-bar__reset",
						type: "button",
						onClick: () => {
							j(""), N("all"), F("all"), L("all"), z(""), U(""), te("recent");
						},
						children: "초기화"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "briefing-archive-feed",
				"aria-label": "저장 브리핑",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-section-heading",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "Saved Briefings"
					}), /* @__PURE__ */ (0, K.jsx)("h2", { children: "저장된 브리핑" })] }), /* @__PURE__ */ (0, K.jsx)("span", {
						"aria-live": "polite",
						children: s ? "불러오는 중..." : `${ce.length}건${A ? " · 검색 결과" : ""}`
					})]
				}), le.length ? le.map((e) => /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "briefing-archive-date-group",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-feed-group-head",
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-name",
							children: e.label
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-meta",
							children: hn(e.rows.length, e.rows[0]?.generatedAt)
						})]
					}), e.rows.map((e) => {
						let t = Ti(e), n = g === `delete-${t.date}-${t.scope}-${t.kind}`;
						return /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "briefing-archive-card-wrap",
							children: [/* @__PURE__ */ (0, K.jsxs)("button", {
								type: "button",
								className: `briefing-archive-card is-${t.scope}`,
								onClick: () => t.date && Mi(t.date, t.scope, t.kind),
								children: [
									/* @__PURE__ */ (0, K.jsxs)("span", {
										className: "briefing-archive-card-meta",
										children: [
											/* @__PURE__ */ (0, K.jsx)("span", {
												className: "briefing-archive-market",
												children: gi[t.scope]
											}),
											t.chips.map((e) => /* @__PURE__ */ (0, K.jsx)("span", {
												className: "chip briefing-archive-chip",
												children: e
											}, e)),
											t.engine && /* @__PURE__ */ (0, K.jsx)("span", {
												className: "chip briefing-archive-chip",
												children: t.engine
											})
										]
									}),
									/* @__PURE__ */ (0, K.jsx)("strong", { children: t.title }),
									/* @__PURE__ */ (0, K.jsx)("span", {
										className: "briefing-archive-card-foot",
										children: t.foot
									})
								]
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								className: "btn btn--icon briefing-archive-card-delete",
								disabled: n,
								onClick: () => ie(t.date, t.scope, t.kind),
								"aria-label": `${t.date} ${yi[t.kind]} 브리핑 삭제`,
								"data-tooltip": "삭제",
								"data-tooltip-pos": "bottom",
								children: /* @__PURE__ */ (0, K.jsx)("svg", {
									width: "14",
									height: "14",
									viewBox: "0 0 16 16",
									fill: "none",
									stroke: "currentColor",
									strokeWidth: "1.4",
									strokeLinecap: "round",
									strokeLinejoin: "round",
									"aria-hidden": "true",
									children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" })
								})
							})]
						}, e.id || `${t.date}-${t.scope}-${t.kind}`);
					})]
				}, e.label)) : /* @__PURE__ */ (0, K.jsx)("div", {
					className: "briefing-archive-empty",
					children: "조건에 맞는 저장 브리핑이 없습니다."
				})]
			})
		]
	});
}
//#endregion
//#region src/app/routes.ts
var Gi = [
	{
		id: "home",
		label: "홈",
		group: "home"
	},
	{
		id: "dashboard",
		label: "대시보드",
		group: "home"
	},
	{
		id: "briefing",
		label: "브리핑",
		group: "research"
	},
	{
		id: "rss",
		label: "RSS 피드",
		group: "research"
	},
	{
		id: "market-memory",
		label: "시장 내러티브",
		group: "research"
	},
	{
		id: "analysis",
		label: "기업 분석",
		group: "research"
	},
	{
		id: "deep-research",
		label: "딥 리서치",
		group: "research"
	},
	{
		id: "watchlist",
		label: "워치리스트",
		group: "home"
	},
	{
		id: "portfolio",
		label: "포트폴리오",
		group: "portfolio"
	},
	{
		id: "settings",
		label: "설정",
		group: "system"
	}
], Ki = Gi.filter((e) => e.visibleInNav !== !1), qi = "home";
function Ji(e) {
	let t = e.replace(/^#\/?/, "").split("/")[0];
	return Gi.some((e) => e.id === t) ? t : qi;
}
function Yi(e) {
	return `#/${e}`;
}
function Xi(e) {
	return Gi.find((t) => t.id === e) ?? Gi[0];
}
//#endregion
//#region src/app/CommandPalette.tsx
function Zi(e) {
	return e === "home" ? "Agent Home" : e === "dashboard" ? "위젯과 하단 대시보드" : e === "briefing" ? "저장 브리핑과 생성" : e === "rss" ? "RSS 수집 자료" : e === "market-memory" ? "중기 시장 내러티브" : e === "analysis" ? "기업 분석 보고서" : e === "deep-research" ? "딥 리서치 보고서" : e === "watchlist" ? "워치리스트" : "설정";
}
var Qi = [
	"us",
	"kr",
	"europe",
	"jp",
	"all",
	"both"
];
function $i(e) {
	return e && Qi.includes(e) ? e : "both";
}
function ea(e) {
	return e.reportDate || e.date || "";
}
function ta() {
	let [e, t] = (0, l.useState)(!1), [n, r] = (0, l.useState)(""), [i, a] = (0, l.useState)(0), [o, s] = (0, l.useState)(null), c = (0, l.useRef)(null), u = (0, l.useRef)(null), d = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		if (!e || o) return;
		let t = !0;
		return B("/api/dashboard").then((e) => {
			t && s(e);
		}).catch(() => {
			t && s({ briefings: [] });
		}), () => {
			t = !1;
		};
	}, [o, e]), (0, l.useEffect)(() => {
		if (document.body.classList.toggle("command-palette-open", e), !e) return;
		let t = window.requestAnimationFrame(() => c.current?.focus());
		return () => {
			window.cancelAnimationFrame(t), document.body.classList.remove("command-palette-open");
		};
	}, [e]);
	let f = (0, l.useMemo)(() => {
		let e = Ki.map((e) => ({
			id: `route:${e.id}`,
			title: e.label,
			subtitle: Zi(e.id),
			type: "화면",
			qa: e.id === "deep-research" ? "command-deep-research" : void 0,
			run: () => {
				window.location.hash = Yi(e.id);
			}
		})), t = (o?.briefings || []).slice(0, 12).map((e) => {
			let t = ea(e), n = $i(e.marketScope || e.scope);
			return {
				id: `briefing:${t}:${n}`,
				title: e.title || `${t} 시장 브리핑`,
				subtitle: [t, n.toUpperCase()].filter(Boolean).join(" · "),
				type: "브리핑",
				run: () => {
					t && (window.location.hash = `#/briefing/${t}/${n}`);
				}
			};
		});
		return [
			{
				id: "action:agent",
				title: "AI Agent 열기",
				subtitle: "현재 화면 컨텍스트로 Agent Dock을 엽니다.",
				type: "액션",
				run: () => nt({ surface: "command_palette" })
			},
			...e,
			...t
		];
	}, [o?.briefings]), p = (0, l.useMemo)(() => {
		let e = n.trim().toLowerCase();
		return (e ? f.filter((t) => `${t.title} ${t.subtitle} ${t.type}`.toLowerCase().includes(e)) : f).slice(0, 40);
	}, [f, n]);
	(0, l.useEffect)(() => {
		a((e) => Math.min(e, Math.max(0, p.length - 1)));
	}, [p.length]);
	function m(e = !0) {
		t(!1), r(""), a(0);
		let n = d.current;
		d.current = null, e && n && window.requestAnimationFrame(() => n.focus({ preventScroll: !0 }));
	}
	function h(e = i) {
		let t = p[e];
		t && (t.run(), m(!1));
	}
	return (0, l.useEffect)(() => {
		let n = (n) => {
			let r = n.key || "";
			if ((n.ctrlKey || n.metaKey) && r.toLowerCase() === "k") {
				n.preventDefault(), e ? m() : (d.current = document.activeElement instanceof HTMLElement ? document.activeElement : null, t(!0));
				return;
			}
			if (e) {
				if (r === "Escape") {
					n.preventDefault(), m();
					return;
				}
				if (r === "ArrowDown") {
					n.preventDefault(), a((e) => Math.min(Math.max(0, p.length - 1), e + 1));
					return;
				}
				if (r === "ArrowUp") {
					n.preventDefault(), a((e) => Math.max(0, e - 1));
					return;
				}
				if (r === "Enter") {
					n.preventDefault(), h();
					return;
				}
				if (r === "Tab") {
					let e = u.current, t = e ? Array.from(e.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex=\"-1\"])")).filter((e) => !e.hidden && e.getAttribute("aria-hidden") !== "true") : [];
					if (!t.length) {
						n.preventDefault(), e?.focus({ preventScroll: !0 });
						return;
					}
					let r = t[0], i = t[t.length - 1];
					n.shiftKey && document.activeElement === r ? (n.preventDefault(), i.focus()) : !n.shiftKey && document.activeElement === i && (n.preventDefault(), r.focus());
				}
			}
		};
		return document.addEventListener("keydown", n), () => document.removeEventListener("keydown", n);
	}, [
		i,
		p,
		e
	]), e ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "command-palette react-command-palette",
		"data-react-command-palette": !0,
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "command-backdrop",
			type: "button",
			"aria-label": "명령 팔레트 닫기",
			onClick: () => m()
		}), /* @__PURE__ */ (0, K.jsxs)("section", {
			ref: u,
			className: "command-dialog",
			role: "dialog",
			"aria-modal": "true",
			"aria-labelledby": "reactCommandPaletteTitle",
			tabIndex: -1,
			children: [
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "command-input-row",
					children: [/* @__PURE__ */ (0, K.jsx)("span", {
						className: "command-mark",
						"aria-hidden": "true",
						children: "⌘K"
					}), /* @__PURE__ */ (0, K.jsx)("input", {
						ref: c,
						value: n,
						onChange: (e) => {
							r(e.currentTarget.value), a(0);
						},
						placeholder: "화면, 보고서, 액션 검색",
						"aria-label": "명령 검색"
					})]
				}),
				/* @__PURE__ */ (0, K.jsx)("h2", {
					id: "reactCommandPaletteTitle",
					children: "명령 팔레트"
				}),
				/* @__PURE__ */ (0, K.jsx)("div", {
					className: "command-list",
					role: "listbox",
					"aria-label": "명령 목록",
					children: p.length ? p.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("button", {
						className: "command-item",
						type: "button",
						"data-qa": e.qa,
						role: "option",
						"aria-selected": t === i,
						onMouseEnter: () => a(t),
						onClick: () => h(t),
						children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "command-item-title",
							children: e.title
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "command-item-subtitle",
							children: e.subtitle
						})] }), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "command-item-type",
							children: e.type
						})]
					}, e.id)) : /* @__PURE__ */ (0, K.jsx)("div", {
						className: "command-empty",
						children: "검색 결과가 없습니다."
					})
				}),
				/* @__PURE__ */ (0, K.jsx)("div", {
					className: "command-footer",
					children: "Ctrl/⌘ K로 열고, Enter로 실행합니다."
				})
			]
		})]
	}) : null;
}
//#endregion
//#region src/app/companyAnalysis/useCompanyResolution.ts
var na = 250;
function ra(e, t) {
	let n = t?.preferHome === !0, [r, i] = (0, l.useState)(null), [a, o] = (0, l.useState)(!1), [s, c] = (0, l.useState)(null), u = (0, l.useRef)(0), d = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		let t = e.trim();
		if (t.length < 1) {
			i(null), o(!1);
			return;
		}
		let r = u.current + 1;
		u.current = r, o(!0);
		let a = window.setTimeout(() => {
			(async () => {
				try {
					let e = await B(`/api/company/resolve?q=${encodeURIComponent(t)}&limit=6${n ? "&prefer=home" : ""}`);
					if (u.current !== r) return;
					i(e);
				} catch {
					if (u.current !== r) return;
					i(null);
				} finally {
					u.current === r && o(!1);
				}
			})();
		}, na);
		return () => window.clearTimeout(a);
	}, [e, n]);
	let f = (0, l.useCallback)((e, t) => {
		d.current = e && t !== void 0 ? t : null, c(e);
	}, []);
	return (0, l.useEffect)(() => {
		(d.current === null || d.current !== e) && (d.current = null, c(null));
	}, [e]), {
		resolution: r,
		pending: a,
		picked: s,
		setPicked: c,
		pick: f,
		effective: s || (r?.status === "confident" ? r.match : null)
	};
}
//#endregion
//#region src/app/reportReader/AnalysisCharts.tsx
var ia = [
	"var(--folio-chart-1)",
	"var(--folio-chart-2)",
	"var(--folio-chart-3)",
	"var(--folio-chart-4)",
	"var(--folio-chart-5)"
], aa = {
	revenue: "매출",
	grossProfit: "매출총이익",
	operatingIncome: "영업이익",
	netIncome: "순이익",
	operatingCashFlow: "영업활동 현금흐름",
	capitalExpenditure: "설비투자",
	freeCashFlow: "잉여현금흐름",
	grossMargin: "매출총이익률",
	operatingMargin: "영업이익률",
	netMargin: "순이익률",
	fcfMargin: "잉여현금흐름률"
};
function oa(e) {
	return typeof e == "number" && Number.isFinite(e) ? e : null;
}
function sa(e) {
	return Array.isArray(e) ? e.map(oa) : [];
}
function ca(e) {
	let t = String(e || "USD").toUpperCase();
	return t === "KRW" || t === "KRX" ? "₩" : t === "JPY" ? "¥" : t === "EUR" ? "€" : t === "GBP" ? "£" : "$";
}
function la(e, t = "plain", n) {
	if (e === null) return "-";
	if (t === "percent") return `${(e * 100).toFixed(1)}%`;
	if (t === "money") {
		let t = ca(n), r = Math.abs(e);
		return r >= 0xe8d4a51000 ? `${t}${(e / 0xe8d4a51000).toFixed(1)}T` : r >= 1e9 ? `${t}${(e / 1e9).toFixed(1)}B` : r >= 1e6 ? `${t}${(e / 1e6).toFixed(1)}M` : `${t}${e.toLocaleString(void 0, { maximumFractionDigits: 2 })}`;
	}
	return e.toFixed(Math.abs(e) >= 100 ? 0 : 1);
}
function ua(e) {
	return ({
		performance: [
			["revenue", "money"],
			["operatingIncome", "money"],
			["netIncome", "money"],
			["netMargin", "percent"]
		],
		quarterly: [
			["revenue", "money"],
			["operatingIncome", "money"],
			["netIncome", "money"],
			["netMargin", "percent"]
		],
		cashflow: [
			["operatingCashFlow", "money"],
			["freeCashFlow", "money"],
			["capitalExpenditure", "money"]
		],
		margins: [
			["grossMargin", "percent"],
			["operatingMargin", "percent"],
			["netMargin", "percent"]
		]
	}[String(e.kind || e.id || "")] || []).map(([t, n]) => ({
		key: t,
		label: aa[t] || t,
		values: sa(e[t]),
		kind: n
	})).filter((e) => e.values.some((e) => e !== null));
}
function da(e) {
	let t = e.filter((e) => e !== null);
	if (!t.length) return {
		min: 0,
		max: 1
	};
	let n = Math.min(0, ...t), r = Math.max(0, ...t);
	return n === r ? {
		min: n - 1,
		max: r + 1
	} : {
		min: n,
		max: r
	};
}
function fa(e, t, n, r = 16, i = 150) {
	return r + (1 - (e - t) / (n - t)) * i;
}
var pa = {
	height: 300,
	top: 20,
	plot: 212,
	left: 58,
	right: 50
}, ma = 980, ha = 200;
function ga() {
	let e = (0, l.useRef)(null), [t, n] = (0, l.useState)(520);
	(0, l.useLayoutEffect)(() => {
		let t = e.current;
		if (!t) return;
		let r = (e) => {
			e > 0 && n(Math.round(e));
		};
		r(t.getBoundingClientRect().width);
		let i = () => r(t.getBoundingClientRect().width);
		window.addEventListener("resize", i);
		let a = typeof ResizeObserver > "u" ? null : new ResizeObserver((e) => r(e[0]?.contentRect.width ?? 0));
		return a?.observe(t), () => {
			window.removeEventListener("resize", i), a?.disconnect();
		};
	}, []);
	let r = Math.max(ha, Math.min(ma, t));
	return {
		ref: e,
		width: r,
		offset: Math.max(0, Math.round((t - r) / 2))
	};
}
function _a(e) {
	let t = 0;
	for (let n of e) t += /[ᄀ-ᇿ　-ヿ一-鿿가-힯＀-￯]/.test(n) ? 13 : 7.2;
	return t;
}
function va(e, t) {
	let n = e.reduce((e, t) => Math.max(e, _a(t)), 0);
	return Math.max(1, Math.ceil((n + 6) / Math.max(1, t)));
}
function ya(e, t, n) {
	let r = /^(\d{4})\s+Q([1-4])$/.exec(String(e[t] ?? "").trim());
	if (r) {
		let t = `${Number(r[1]) - 1} Q${r[2]}`;
		return e.findIndex((e) => String(e ?? "").trim() === t);
	}
	let i = t - (Number(n) > 0 ? Number(n) : 1);
	return i >= 0 ? i : -1;
}
function ba(e, t, n = 4) {
	if (!Number.isFinite(e) || !Number.isFinite(t) || e === t) return [e, t];
	let r = (t - e) / n;
	return Array.from({ length: n + 1 }, (t, n) => e + r * n);
}
function xa({ chart: e, series: t, activeIndex: n, onIndex: r, width: i }) {
	let a = Array.isArray(e.years) ? e.years : [], o = t.filter((e) => e.kind !== "percent"), s = t.filter((e) => e.kind === "percent"), { min: c, max: l } = da(o.flatMap((e) => e.values)), u = da(s.flatMap((e) => e.values)), { height: d, top: f, plot: p, left: m, right: h } = pa, g = (i - m - h) / Math.max(1, a.length), _ = Math.max(6, Math.min(g / (o.length + 1.6), (g - 18) / Math.max(1, o.length))), v = fa(0, c, l, f, p), y = (e) => m + e * g + g / 2, b = va(a, g);
	return /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "analysis-chart-svg",
		width: i,
		height: d,
		viewBox: `0 0 ${i} ${d}`,
		role: "img",
		"aria-label": e.title || "기업 분석 차트",
		children: [
			a.map((e, t) => /* @__PURE__ */ (0, K.jsx)("rect", {
				className: "analysis-chart-band",
				"data-active": t === n ? "true" : void 0,
				x: m + t * g,
				y: f - 4,
				width: g,
				height: p + 8
			}, `band-${e}`)),
			ba(c, l).map((t) => {
				let n = fa(t, c, l, f, p);
				return /* @__PURE__ */ (0, K.jsxs)("g", { children: [/* @__PURE__ */ (0, K.jsx)("line", {
					x1: m,
					y1: n,
					x2: i - h,
					y2: n,
					stroke: "var(--folio-border)",
					strokeWidth: "0.5"
				}), /* @__PURE__ */ (0, K.jsx)("text", {
					className: "analysis-chart-axis",
					x: m - 8,
					y: n + 4,
					textAnchor: "end",
					children: la(t, "money", e.currency)
				})] }, `tick-${t}`);
			}),
			s.length > 0 && ba(u.min, u.max, 2).map((e) => /* @__PURE__ */ (0, K.jsx)("text", {
				className: "analysis-chart-axis",
				x: i - h + 8,
				y: fa(e, u.min, u.max, f, p) + 4,
				children: la(e, "percent")
			}, `rate-${e}`)),
			a.map((e, t) => o.map((n, r) => {
				let i = n.values[t];
				if (i === null) return null;
				let a = fa(i, c, l, f, p), s = y(t) - o.length * _ / 2 + r * _;
				return /* @__PURE__ */ (0, K.jsx)("rect", {
					x: s,
					y: Math.min(a, v),
					width: Math.max(2, _ - 3),
					height: Math.max(2, Math.abs(v - a)),
					rx: "3",
					fill: ia[r % ia.length]
				}, `${n.key}-${e}`);
			})),
			s.map((e, t) => {
				let n = a.map((t, n) => [y(n), e.values[n]]).filter((e) => e[1] !== null).map(([e, t]) => `${e},${fa(t, u.min, u.max, f, p)}`).join(" ");
				return n ? /* @__PURE__ */ (0, K.jsx)("polyline", {
					points: n,
					fill: "none",
					strokeWidth: "2",
					stroke: ia[(o.length + t) % ia.length]
				}, e.key) : null;
			}),
			a.map((e, t) => t === n || (a.length - 1 - t) % b == 0 ? /* @__PURE__ */ (0, K.jsx)("text", {
				className: "analysis-chart-axis",
				"data-active": t === n ? "true" : void 0,
				x: y(t),
				y: d - 16,
				textAnchor: "middle",
				children: e
			}, `x-${e}`) : null),
			a.length > 0 && /* @__PURE__ */ (0, K.jsx)("rect", {
				className: "analysis-chart-marker",
				x: m + n * g + g * .2,
				y: f + p + 6,
				width: g * .6,
				height: 2,
				rx: "1"
			}),
			a.map((e, t) => /* @__PURE__ */ (0, K.jsx)("rect", {
				className: "analysis-chart-hit",
				x: m + t * g,
				y: f - 4,
				width: g,
				height: p + 8,
				tabIndex: 0,
				role: "button",
				"aria-label": `${e} 수치 보기`,
				onMouseEnter: () => r(t, y(t)),
				onFocus: () => r(t, y(t))
			}, `hit-${e}`))
		]
	});
}
function Sa({ chart: e, series: t, activeIndex: n, onIndex: r, width: i }) {
	let a = Array.isArray(e.years) ? e.years : [], { min: o, max: s } = da(t.flatMap((e) => e.values)), { height: c, top: l, plot: u, left: d, right: f } = pa, p = (i - d - f) / Math.max(1, a.length - 1), m = (e) => d + e * p, h = va(a, p);
	return /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "analysis-chart-svg",
		width: i,
		height: c,
		viewBox: `0 0 ${i} ${c}`,
		role: "img",
		"aria-label": e.title || "기업 분석 차트",
		children: [
			ba(o, s).map((n) => {
				let r = fa(n, o, s, l, u);
				return /* @__PURE__ */ (0, K.jsxs)("g", { children: [/* @__PURE__ */ (0, K.jsx)("line", {
					x1: d,
					y1: r,
					x2: i - f,
					y2: r,
					stroke: "var(--folio-border)",
					strokeWidth: "0.5"
				}), /* @__PURE__ */ (0, K.jsx)("text", {
					className: "analysis-chart-axis",
					x: d - 8,
					y: r + 4,
					textAnchor: "end",
					children: la(n, t[0]?.kind || "percent", e.currency)
				})] }, `tick-${n}`);
			}),
			a.length > 0 && /* @__PURE__ */ (0, K.jsx)("line", {
				className: "analysis-chart-rule",
				x1: m(n),
				y1: l - 4,
				x2: m(n),
				y2: l + u + 4
			}),
			t.map((e, t) => {
				let r = e.values.map((e, t) => e === null ? null : `${m(t)},${fa(e, o, s, l, u)}`).filter(Boolean).join(" "), i = e.values[n];
				return /* @__PURE__ */ (0, K.jsxs)("g", { children: [/* @__PURE__ */ (0, K.jsx)("polyline", {
					points: r,
					fill: "none",
					stroke: ia[t % ia.length],
					strokeWidth: "2",
					strokeLinejoin: "round",
					strokeLinecap: "round"
				}), i != null && /* @__PURE__ */ (0, K.jsx)("circle", {
					cx: m(n),
					cy: fa(i, o, s, l, u),
					r: "4",
					fill: ia[t % ia.length]
				})] }, e.key);
			}),
			a.map((e, t) => t === n || (a.length - 1 - t) % h == 0 ? /* @__PURE__ */ (0, K.jsx)("text", {
				className: "analysis-chart-axis",
				x: m(t),
				y: c - 16,
				textAnchor: "middle",
				children: e
			}, `x-${e}`) : null),
			a.map((e, t) => /* @__PURE__ */ (0, K.jsx)("rect", {
				className: "analysis-chart-hit",
				x: t === 0 ? d : m(t) - p / 2,
				y: l - 4,
				width: t === 0 || t === a.length - 1 ? p / 2 : p,
				height: u + 8,
				tabIndex: 0,
				role: "button",
				"aria-label": `${e} 수치 보기`,
				onMouseEnter: () => r(t, m(t)),
				onFocus: () => r(t, m(t))
			}, `hit-${e}`))
		]
	});
}
function Ca({ chart: e, onPoint: t, onLeave: n }) {
	let r = Array.isArray(e.scenarios) ? e.scenarios : [], { max: i } = da(r.map((e) => oa(e.perShare ?? e.price))), a = oa(e.currentPrice);
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "analysis-scenario-bars",
		children: [r.map((r, a) => {
			let o = oa(r.perShare ?? r.price), s = o === null || i <= 0 ? 0 : Math.max(4, Math.min(100, o / i * 100)), c = String(r.name || r.label || `Scenario ${a + 1}`), l = la(o, "money", e.currency);
			return /* @__PURE__ */ (0, K.jsxs)("div", {
				"aria-label": `${c} ${l}`,
				className: "analysis-scenario-row",
				onBlur: n,
				onFocus: () => t({
					label: c,
					value: l
				}),
				onMouseEnter: () => t({
					label: c,
					value: l
				}),
				onMouseLeave: n,
				tabIndex: 0,
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", { children: c }),
					/* @__PURE__ */ (0, K.jsx)("div", { children: /* @__PURE__ */ (0, K.jsx)("i", { style: {
						width: `${s}%`,
						background: ia[a % ia.length]
					} }) }),
					/* @__PURE__ */ (0, K.jsx)("strong", { children: l })
				]
			}, c);
		}), a !== null && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "analysis-chart-note",
			children: ["현재가: ", la(a, "money", e.currency)]
		})]
	});
}
function wa(e) {
	let t = Array.isArray(e.labels) ? e.labels : [], n = Object.entries(e.series || {}).map(([e, t]) => ({
		key: e,
		label: e,
		values: Array.isArray(t) ? t.map((e) => typeof e == "number" ? e / 100 : null) : [],
		kind: "percent"
	}));
	return {
		chart: {
			...e,
			years: t
		},
		series: n
	};
}
function Ta({ chart: e, series: t, index: n }) {
	let r = Array.isArray(e.years) ? e.years : [], i = ya(r, n, e.compareOffset), a = i >= 0 ? r[i] : "";
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "analysis-chart-readout",
		children: [/* @__PURE__ */ (0, K.jsxs)("p", {
			className: "analysis-chart-readout-head",
			children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: r[n] || "" }), a && /* @__PURE__ */ (0, K.jsxs)("span", { children: [a, " 대비"] })]
		}), t.map((t, r) => {
			let a = t.values[n] ?? null, o = i >= 0 ? t.values[i] ?? null : null, s = "—", c = "flat";
			if (a !== null && o !== null && o !== 0) if (t.kind === "percent") {
				let e = (a - o) * 100;
				c = e >= 0 ? "up" : "down", s = `${e >= 0 ? "+" : ""}${e.toFixed(1)}%p`;
			} else {
				let e = (a - o) / Math.abs(o) * 100;
				c = e >= 0 ? "up" : "down", s = `${e >= 0 ? "+" : ""}${e.toFixed(1)}%`;
			}
			return /* @__PURE__ */ (0, K.jsxs)("p", {
				className: "analysis-chart-readout-row",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "analysis-chart-swatch",
						style: { background: ia[r % ia.length] }
					}),
					/* @__PURE__ */ (0, K.jsx)("span", { children: t.label }),
					/* @__PURE__ */ (0, K.jsx)("b", { children: la(a, t.kind, e.currency) }),
					/* @__PURE__ */ (0, K.jsx)("em", {
						"data-direction": c,
						children: s
					})
				]
			}, t.key);
		})]
	});
}
function Ea({ chart: e }) {
	let [t, n] = (0, l.useState)(null), r = String(e.kind || e.id || ""), i = r === "margins" ? {
		chart: e,
		series: ua(e)
	} : r === "price_return" ? wa(e) : null, a = [
		"performance",
		"cashflow",
		"quarterly"
	].includes(r) ? {
		chart: e,
		series: ua(e)
	} : null, o = i ?? a, s = o?.series ?? [], c = Array.isArray(o?.chart.years) ? o?.chart.years : [], [u, d] = (0, l.useState)(null), [f, p] = (0, l.useState)(null), m = ga(), h = (e, t) => {
		d(e), p(t);
	}, g = Math.max(0, c.length - 1), _ = Math.min(u ?? g, g), v = t?.x === void 0 ? void 0 : {
		left: `${Math.max(7, Math.min(93, t.x / m.width * 100))}%`,
		top: `${Math.max(10, t.y || 10)}px`
	};
	return /* @__PURE__ */ (0, K.jsxs)("article", {
		className: "analysis-chart-card",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "analysis-chart-title",
				children: [/* @__PURE__ */ (0, K.jsx)("h4", { children: e.title || "기업 분석 차트" }), e.subtitle && /* @__PURE__ */ (0, K.jsx)("p", { children: e.subtitle })]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "analysis-chart-plot",
				onBlur: () => p(null),
				onMouseLeave: () => p(null),
				ref: m.ref,
				children: [
					i && i.series.length ? /* @__PURE__ */ (0, K.jsx)(Sa, {
						chart: i.chart,
						series: i.series,
						activeIndex: _,
						onIndex: h,
						width: m.width
					}) : null,
					a && a.series.length ? /* @__PURE__ */ (0, K.jsx)(xa, {
						chart: a.chart,
						series: a.series,
						activeIndex: _,
						onIndex: h,
						width: m.width
					}) : null,
					r === "dcf" || r === "scenario_price" ? /* @__PURE__ */ (0, K.jsx)(Ca, {
						chart: e,
						onPoint: n,
						onLeave: () => n(null)
					}) : null,
					!s.length && !["dcf", "scenario_price"].includes(r) && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "analysis-chart-warning",
						children: "이 차트에 표시할 수치가 충분하지 않습니다."
					}),
					t && /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "analysis-chart-tooltip",
						style: v,
						children: [
							t.series && /* @__PURE__ */ (0, K.jsx)("span", { children: t.series }),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: t.value }),
							/* @__PURE__ */ (0, K.jsx)("em", { children: t.label })
						]
					}),
					f !== null && o && s.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "analysis-chart-hover",
						"data-side": f > m.width / 2 ? "left" : "right",
						style: f > m.width / 2 ? { right: `calc(100% - ${f + m.offset}px)` } : { left: `${f + m.offset}px` },
						children: [/* @__PURE__ */ (0, K.jsx)("b", { children: c[_] || "" }), s.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("p", { children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "analysis-chart-swatch",
								style: { background: ia[t % ia.length] }
							}),
							/* @__PURE__ */ (0, K.jsx)("span", { children: e.label }),
							/* @__PURE__ */ (0, K.jsx)("em", { children: la(e.values[_] ?? null, e.kind, o.chart.currency) })
						] }, e.key))]
					})
				]
			}),
			o && s.length > 0 ? /* @__PURE__ */ (0, K.jsx)(Ta, {
				chart: o.chart,
				series: s,
				index: _
			}) : null
		]
	});
}
function Da({ payload: e, chartIds: t, heading: n = "기업 분석 시각화", intro: r = "저장된 공식 재무 데이터와 시장 데이터를 기반으로 생성된 참고 차트입니다.", compact: i = !1 }) {
	let a = t ? new Set(t) : null, o = (Array.isArray(e?.charts) ? e.charts : []).filter((e) => !a || a.has(String(e.id || e.kind || "")));
	return !e?.available || !o.length ? null : /* @__PURE__ */ (0, K.jsxs)("section", {
		className: `analysis-charts-panel analysis-charts-inline${i ? " compact" : ""}`,
		"aria-label": n,
		children: [/* @__PURE__ */ (0, K.jsx)("div", {
			className: "analysis-chart-head",
			children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "section-kicker",
					children: "Company Visuals"
				}),
				/* @__PURE__ */ (0, K.jsx)("h3", { children: n }),
				/* @__PURE__ */ (0, K.jsx)("p", { children: r })
			] })
		}), /* @__PURE__ */ (0, K.jsx)("div", {
			className: "analysis-chart-grid",
			children: o.map((e, t) => /* @__PURE__ */ (0, K.jsx)(Ea, { chart: e }, e.id || `${e.title || "chart"}-${t}`))
		})]
	});
}
//#endregion
//#region src/app/reportReader/CompanyAnalysisBody.tsx
var Oa = [
	{
		ids: ["performance", "margins"],
		patterns: [/실적|재무|수익성|숫자|손익/i],
		fallbackIndex: 1
	},
	{
		ids: ["cashflow"],
		patterns: [/현금|cash|fcf|free cash|설비투자/i],
		fallbackIndex: 2
	},
	{
		ids: ["dcf", "scenario_price"],
		patterns: [/밸류에이션|가치|valuation|가격|적정가/i],
		fallbackIndex: 3
	},
	{
		ids: ["price_return"],
		patterns: [/주가|시장|접근|핵심 판단|수익률/i],
		fallbackIndex: 0
	}
];
function ka(e = "") {
	let t = e.replace(/\r\n/g, "\n").trim();
	if (!t) return [];
	let n = Array.from(t.matchAll(/^##\s+(.+)$/gm));
	if (!n.length) return [{
		key: "body",
		title: "",
		markdown: t
	}];
	let r = [], i = n[0].index || 0;
	if (i > 0) {
		let e = t.slice(0, i).trim();
		e && r.push({
			key: "intro",
			title: "",
			markdown: e
		});
	}
	return n.forEach((e, i) => {
		let a = e.index || 0, o = i + 1 < n.length && n[i + 1].index || t.length, s = t.slice(a, o).trim();
		r.push({
			key: `section-${i}`,
			title: e[1] || "",
			markdown: s
		});
	}), r;
}
function Aa(e) {
	return new Set((Array.isArray(e?.charts) ? e.charts : []).map((e) => String(e?.id || e?.kind || "")).filter(Boolean));
}
function ja(e, t, n, r = /* @__PURE__ */ new Set()) {
	let i = Aa(n), a = e.title, o = [];
	for (let e of Oa) if (e.patterns.some((e) => e.test(a)) || e.fallbackIndex === t) for (let t of e.ids) i.has(t) && !r.has(t) && o.push(t);
	return o;
}
function Ma(e, t = /* @__PURE__ */ new Set()) {
	return Array.from(Aa(e)).filter((e) => !t.has(e));
}
function Na({ markdown: e, charts: t }) {
	let n = ka(e), r = /* @__PURE__ */ new Set();
	return n.length ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [n.map((e, n) => {
		let i = ja(e, n, t, r);
		return i.forEach((e) => r.add(e)), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "company-analysis-section",
			children: [/* @__PURE__ */ (0, K.jsx)(On, { markdown: e.markdown }), i.length > 0 && /* @__PURE__ */ (0, K.jsx)(Da, {
				payload: t,
				chartIds: i,
				heading: "관련 시각화",
				intro: "이 섹션의 판단을 확인할 때 함께 볼 수 있는 수치입니다.",
				compact: !0
			})]
		}, e.key);
	}), Ma(t, r).length > 0 && /* @__PURE__ */ (0, K.jsx)(Da, {
		payload: t,
		chartIds: Ma(t, r),
		heading: "추가 시각화",
		intro: "본문 섹션에 직접 매칭되지 않은 보조 차트입니다.",
		compact: !0
	})] }) : /* @__PURE__ */ (0, K.jsx)(Da, { payload: t });
}
//#endregion
//#region src/app/watchlistEarnings.ts
function Pa(e) {
	return String(e.status || "").toLowerCase() !== "confirmed";
}
function Fa(e, t = /* @__PURE__ */ new Date()) {
	let n = new Date(e);
	if (Number.isNaN(n.getTime())) return null;
	let r = (e) => Date.UTC(e.getFullYear(), e.getMonth(), e.getDate());
	return Math.round((r(n) - r(t)) / 864e5);
}
function Ia(e, t = /* @__PURE__ */ new Date()) {
	let n = Fa(e, t);
	return n == null || n < 0 ? "" : n === 0 ? "D-DAY" : `D-${n}`;
}
function La(e) {
	return String(e || "").slice(0, 10).replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1.$2.$3");
}
function Ra(e, t = /* @__PURE__ */ new Date()) {
	let n = {};
	for (let r of e || []) {
		if (String(r.kind || "") !== "earnings") continue;
		let e = String(r.startsAt || ""), i = Fa(e, t);
		if (!(i == null || i < 0)) for (let t of r.tickers || []) {
			let i = String(t || "").toUpperCase();
			if (!i) continue;
			let a = n[i];
			(!a || e < String(a.startsAt || "")) && (n[i] = r);
		}
	}
	return n;
}
function za(e) {
	let t = (e) => String(e).padStart(2, "0");
	return `${e.getFullYear()}-${t(e.getMonth() + 1)}-${t(e.getDate())}`;
}
async function Ba(e, t = /* @__PURE__ */ new Date()) {
	let n = [...new Set(e.map((e) => String(e || "").trim()).filter(Boolean))];
	if (!n.length) return {};
	let r = new Date(t.getTime() + 104544e5), i = new URLSearchParams({
		start: za(t),
		end: za(r),
		kind: "earnings",
		limit: "500"
	});
	for (let e of n) i.append("ticker", e);
	try {
		return Ra((await B(`/api/market-calendar?${i}`)).events || [], t);
	} catch {
		return {};
	}
}
//#endregion
//#region src/app/watchlist/EarningsPanel.tsx
var Va = "folio:analysis-query", Ha = {
	estimate: "예측치",
	priorQuarter: "지난 분기",
	priorYear: "작년 동기간"
}, Ua = {
	estimate: "예측치보다",
	priorQuarter: "지난 분기보다",
	priorYear: "작년 동기보다"
}, Wa = [{
	limit: 0xe8d4a51000,
	suffix: "조"
}, {
	limit: 1e8,
	suffix: "억"
}];
function Ga(e, t = "USD") {
	if (e == null || !Number.isFinite(e)) return "—";
	if (t === "KRW" || t === "JPY") {
		for (let t of Wa) if (Math.abs(e) >= t.limit) return `${(e / t.limit).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}${t.suffix}`;
		return e.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
	}
	let n = Math.abs(e) >= 1e9 ? {
		div: 1e9,
		suffix: "B"
	} : Math.abs(e) >= 1e6 ? {
		div: 1e6,
		suffix: "M"
	} : null;
	return n ? `${(e / n.div).toLocaleString("en-US", { maximumFractionDigits: 2 })}${n.suffix}` : e.toLocaleString("en-US", { maximumFractionDigits: 0 });
}
function Ka(e, t = "USD") {
	if (e == null || !Number.isFinite(e)) return "—";
	let n = t === "KRW" || t === "JPY" ? 0 : 2;
	return e.toLocaleString("ko-KR", {
		maximumFractionDigits: n,
		minimumFractionDigits: n
	});
}
function qa(e, t) {
	return e == null || !Number.isFinite(e) || t == null || !Number.isFinite(t) || t === 0 ? null : (e - t) / Math.abs(t);
}
function Ja(e) {
	return e === null ? "—" : `${e > 0 ? "+" : ""}${(e * 100).toFixed(1)}%`;
}
function Ya(e) {
	return e === null || Math.abs(e) < 5e-4 ? "flat" : e > 0 ? "up" : "down";
}
function Xa(e, t) {
	if (t === "priorQuarter") return {
		eps: e.epsPriorQuarter,
		revenue: e.revenuePriorQuarter,
		epsTop: e.epsActual,
		fromStatement: !1
	};
	if (t === "priorYear") {
		let t = e.epsPriorYearBasis === "statement";
		return {
			eps: e.epsPriorYear,
			revenue: e.revenuePriorYear,
			epsTop: t ? e.epsActualStatement : e.epsActual,
			fromStatement: t
		};
	}
	return {
		eps: e.epsEstimate,
		revenue: void 0,
		epsTop: e.epsActual,
		fromStatement: !1
	};
}
function Za(e, t, n, r = Xa(e, t)) {
	let i = `${Ha[t]} ${Ka(r.eps, n)}`;
	return !r.fromStatement || r.eps === null || r.eps === void 0 ? i : r.epsTop === e.epsActual ? `${i} · 손익계산서 기본 EPS 기준` : `${i} · 손익계산서 기본 EPS ${Ka(r.epsTop, n)} 대비`;
}
function Qa({ ticker: e }) {
	let [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)("estimate"), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(!1);
	if ((0, l.useEffect)(() => {
		let t = !0;
		if (!e) {
			n(null);
			return;
		}
		return c(!0), o(""), B(`/api/market/earnings?ticker=${encodeURIComponent(e)}`).then((e) => {
			t && n(e);
		}).catch((e) => {
			t && o(e instanceof Error ? e.message : "실적을 불러오지 못했습니다.");
		}).finally(() => {
			t && c(!1);
		}), () => {
			t = !1;
		};
	}, [e]), !e) return null;
	if (s && !t) return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-earnings-panel",
		children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "실적" }), /* @__PURE__ */ (0, K.jsx)("p", {
			className: "section-subtitle watchlist-earnings-skeleton",
			children: "실적을 불러오는 중입니다."
		})]
	});
	if (a) return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-earnings-panel",
		children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "실적" }), /* @__PURE__ */ (0, K.jsx)("p", {
			className: "section-subtitle",
			children: a
		})]
	});
	let u = t?.currency || "USD", d = t?.next || {}, f = (t?.history || [])[0];
	if (!d.date && !f) return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-earnings-panel",
		children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "실적" }), /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "section-subtitle",
			children: [
				"이 종목의 실적 데이터를 받지 못했습니다. (출처 ",
				t?.provider || "yfinance",
				")"
			]
		})]
	});
	let p = f ? Xa(f, r) : {
		eps: null,
		revenue: null,
		epsTop: null,
		fromStatement: !1
	}, m = f ? qa(p.epsTop, p.eps) : null, h = f ? qa(f.revenueActual, p.revenue) : null;
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-earnings-panel",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-earnings-panel__head",
				children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "실적" }), /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "btn btn--text",
					onClick: () => {
						try {
							window.sessionStorage.setItem(Va, e);
						} catch {}
						window.location.hash = "#/analysis";
					},
					children: "기업분석 열기"
				})]
			}),
			d.date && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-earnings-next",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "watchlist-earnings-next__date",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "section-kicker",
								children: "다음 발표"
							}),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: La(d.date) }),
							Ia(d.date) && /* @__PURE__ */ (0, K.jsx)("span", {
								className: "chip watchlist-earnings-chip",
								"data-estimated": "true",
								children: Ia(d.date)
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("dl", {
						className: "watchlist-earnings-consensus",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "EPS 컨센서스" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: Ka(d.epsEstimate, u) })] }), /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "매출 컨센서스" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: Ga(d.revenueEstimate, u) })] })]
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-subtitle",
						children: "제3자 예정치입니다. 날짜와 컨센서스 모두 회사 IR 공지로 다시 확인하세요."
					})
				]
			}),
			f && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-earnings-recent",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "watchlist-earnings-recent__head",
					children: [/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "section-kicker",
						children: ["최근 발표 · ", f.label || f.quarter]
					}), /* @__PURE__ */ (0, K.jsx)("div", {
						className: "segment",
						role: "group",
						"aria-label": "비교 기준",
						children: Object.keys(Ha).map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"aria-pressed": r === e,
							onClick: () => i(e),
							children: Ha[e]
						}, e))
					})]
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "watchlist-earnings-grid",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "watchlist-earnings-metric",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "section-kicker",
								children: "EPS"
							}),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: Ka(f.epsActual, u) }),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "watchlist-earnings-metric__delta",
								"data-tone": Ya(m),
								children: m === null ? "—" : `${Ua[r]} ${Ja(m)}`
							}),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "watchlist-earnings-metric__base",
								children: Za(f, r, u, p)
							})
						]
					}), /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "watchlist-earnings-metric",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "section-kicker",
								children: "매출"
							}),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: Ga(f.revenueActual, u) }),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "watchlist-earnings-metric__delta",
								"data-tone": Ya(h),
								children: h === null ? "—" : `${Ua[r]} ${Ja(h)}`
							}),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "watchlist-earnings-metric__base",
								children: r === "estimate" ? "매출 컨센서스 없음" : `${Ha[r]} ${Ga(p.revenue, u)}`
							})
						]
					})]
				})]
			}),
			(t?.history || []).length > 1 && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-earnings-history",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					className: "section-kicker",
					children: "지난 발표"
				}), /* @__PURE__ */ (0, K.jsx)("ul", { children: (t?.history || []).slice(1).map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "watchlist-earnings-history__label",
						children: e.label || e.quarter
					}),
					/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "watchlist-earnings-history__eps",
						children: [
							"EPS ",
							Ka(e.epsActual, u),
							e.epsEstimate != null && /* @__PURE__ */ (0, K.jsxs)("small", { children: [" · 예측 ", Ka(e.epsEstimate, u)] })
						]
					}),
					/* @__PURE__ */ (0, K.jsx)("b", {
						"data-tone": Ya(e.surprisePercent ?? null),
						children: Ja(e.surprisePercent ?? null)
					})
				] }, e.quarter || e.label)) })]
			})
		]
	});
}
//#endregion
//#region src/app/CompanyAnalysisRoute.tsx
var $a = [{
	value: "beginner",
	label: "기본",
	description: "쉽게 설명"
}, {
	value: "advanced",
	label: "심화",
	description: "정밀 분석"
}], eo = 20;
function to(e) {
	return new Promise((t) => window.setTimeout(t, e));
}
function no(e) {
	let t = e;
	return !!(t?.id && I(t.status));
}
async function ro(e) {
	let t = e;
	for (; I(t.status);) await to(1e3), t = await B(`/api/jobs/${encodeURIComponent(t.id)}`);
	if (t.status !== "done") throw Error(t.message || t.error || "기업 분석 생성에 실패했습니다.");
	return t;
}
function Y(e = "", t = "기업 분석") {
	let n = e.replace(/\r\n/g, "\n").split("\n"), r = n.findIndex((e) => e.trim());
	if (r < 0) return {
		title: t,
		body: ""
	};
	let i = n[r].trim().match(/^#\s+(.+)$/);
	return i ? {
		title: i[1],
		body: n.slice(r + 1).join("\n").trim()
	} : {
		title: t,
		body: e
	};
}
function X(e) {
	return String(e.company?.ticker || e.query || e.company?.name || "").trim().toUpperCase();
}
function io(e) {
	return String(e.company?.name || e.query || X(e) || "").trim();
}
function ao(e) {
	let t = X(e), n = io(e);
	return t && n && t !== n ? `${t} · ${n}` : n || t || "기업 분석";
}
function oo(e) {
	return Y(String(e.markdown || ""), "").title.trim() || String(e.headline || "").trim() || ao(e);
}
function so(e) {
	return mn(e) || "미상";
}
function co(e) {
	return $a.find((t) => t.value === e)?.label || "";
}
function lo(e) {
	return e === "high" ? "높음" : e === "medium" ? "중간" : e === "low" ? "낮음" : e || "확인 필요";
}
function uo(e) {
	let t = e?.dataGaps;
	return t ? Array.isArray(t) ? t : Array.isArray(t.gaps) ? t.gaps : [] : [];
}
function fo(e) {
	let t = /* @__PURE__ */ new Set();
	return e.filter((e) => {
		let n = [
			ho(e.field),
			ho(e.label),
			ho(e.category),
			ho(e.message || e.suggestedAction)
		].join("|");
		return !t.has(n) && (t.add(n), !0);
	});
}
function po(e) {
	let t = {
		high: 0,
		medium: 1,
		low: 2
	};
	return fo(uo(e).filter((e) => e.status !== "resolved").sort((e, n) => (t[e.severity || ""] ?? 9) - (t[n.severity || ""] ?? 9)));
}
function mo(e) {
	if (!e) return "월 미상";
	let t = new Date(e);
	if (!Number.isNaN(t.getTime())) return `${t.getFullYear()}.${String(t.getMonth() + 1).padStart(2, "0")}`;
	let n = String(e).match(/^(\d{4})[-.](\d{1,2})/);
	return n ? `${n[1]}.${String(n[2]).padStart(2, "0")}` : "월 미상";
}
function ho(e) {
	return String(e || "").trim().toLowerCase();
}
function go(e) {
	return [
		e.source,
		e.date,
		e.type
	].filter(Boolean).join(" · ");
}
function _o(e) {
	return e.title || e.url || e.path || "자료";
}
function vo(e) {
	let t = String(e.markdown || "");
	return e.generation?.webSearch ? t.trim() : t.split(/\n(?=#{1,3}\s*(?:8\.\s*)?(?:Sources Used|사용 자료)\b)/i)[0].trim();
}
function yo(e) {
	window.location.hash = e ? `#/analysis/${encodeURIComponent(e)}` : "#/analysis";
}
function bo() {
	let e = window.location.hash.match(/^#\/?analysis\/(.+)$/);
	return e ? decodeURIComponent(e[1]) : "";
}
function xo() {
	return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "analysis";
}
function So() {
	let e = fn("companyAnalysis"), [t, n] = (0, l.useState)([]), [r, i] = (0, l.useState)(null), [a, o] = (0, l.useState)(() => bo()), [s, c] = (0, l.useState)(""), { resolution: u, pending: d, picked: f, setPicked: p, effective: m } = ra(s), h = f || (u?.status === "confident" ? u.match : null), g = !!(h && !h.cik && (h.market === "EUROPE" || h.market === "JP")), _ = g ? "out-of-scope" : f ? "picked" : d ? "pending" : u?.status || "idle", v = (() => {
		if (!s.trim()) return "티커, 회사명, 한글 표기 중 무엇으로 적어도 됩니다.";
		if (g && h) {
			let e = h.market === "JP" ? "일본" : "유럽";
			return `${h.name}는 ${e} 거래소에만 상장되어 있어 아직 분석할 수 없습니다. 미국에도 상장된 기업은 그 티커로 적어 보세요.`;
		}
		return f ? `${f.name} (${f.ticker})으로 분석합니다.` : d ? "확인 중…" : u ? u.status === "confident" && u.match ? `${u.match.name} (${u.match.ticker})으로 분석합니다.` : u.status === "ambiguous" ? "여러 기업이 맞습니다. 아래에서 고르세요." : "아는 기업이 없습니다. 티커로 적어 보세요. 이대로 진행하면 자료가 거의 없는 보고서가 나옵니다." : "";
	})(), [y, b] = (0, l.useState)("beginner"), [x, S] = (0, l.useState)(""), [C, w] = (0, l.useState)("recent"), [T, E] = (0, l.useState)(!1), [D, O] = (0, l.useState)(!1), [k, A] = (0, l.useState)(""), [j, M] = (0, l.useState)(""), [N, P] = (0, l.useState)(""), [F, I] = (0, l.useState)(0), L = (0, l.useCallback)(async () => {
		E(!0), M("");
		try {
			let e = await B("/api/analysis-reports");
			n(Array.isArray(e) ? e : []), Qe("analysis", {
				surface: "analysis",
				viewId: "analysis",
				reportKind: "",
				reportId: ""
			});
		} catch (e) {
			M(e instanceof Error ? e.message : "기업 분석 목록을 불러오지 못했습니다.");
		} finally {
			E(!1);
		}
	}, []);
	(0, l.useEffect)(() => {
		L();
	}, [L, e]), (0, l.useEffect)(() => {
		let e = () => {
			if (xo()) {
				o(bo());
				try {
					let e = window.sessionStorage.getItem(Va);
					e && (window.sessionStorage.removeItem(Va), c(e));
				} catch {}
			}
		};
		return window.addEventListener("hashchange", e), e(), () => window.removeEventListener("hashchange", e);
	}, []), (0, l.useEffect)(() => {
		let e = (e) => {
			let t = e.detail;
			Re(t, window.FolioAgent?.currentContext) && I((e) => e + 1);
		};
		return window.addEventListener(se, e), () => window.removeEventListener(se, e);
	}, []), (0, l.useEffect)(() => {
		let e = !0;
		async function t(t) {
			E(!0), M("");
			try {
				let n = await B(`/api/analysis-reports/${encodeURIComponent(t)}?includePersonal=true`);
				if (!e) return;
				i(n), Qe("analysis", {
					surface: "analysis_reader",
					viewId: "analysis",
					reportKind: "company_analysis",
					reportId: n.id || t,
					ticker: X(n)
				});
			} catch (t) {
				if (!e) return;
				i(null), M(t instanceof Error ? t.message : "저장된 기업 분석 보고서를 열지 못했습니다.");
			} finally {
				e && E(!1);
			}
		}
		return a ? t(a) : (i(null), Qe("analysis", {
			surface: "analysis",
			viewId: "analysis",
			reportKind: "",
			reportId: ""
		})), () => {
			e = !1;
		};
	}, [a, F]);
	async function R(e) {
		e.preventDefault();
		let t = s.trim();
		if (t) {
			O(!0), M(""), P("기업 자료를 읽고 분석 보고서를 생성하는 중입니다.");
			try {
				let e = await B(`/api/analyze?${new URLSearchParams({
					q: m?.ticker || t,
					analysisStyle: y
				}).toString()}`), n;
				if (no(e)) {
					let t = await ro(e), r = t.result?.reportId || t.result?.artifactId || "";
					if (!r) throw Error("생성된 보고서 ID를 확인하지 못했습니다.");
					n = await B(`/api/analysis-reports/${encodeURIComponent(r)}?includePersonal=true`);
				} else n = e;
				await L(), P("기업 분석 보고서를 생성하고 자동 저장했습니다."), i(n), n.id && yo(n.id);
			} catch (e) {
				M(e instanceof Error ? e.message : "기업 분석 생성에 실패했습니다."), P("");
			} finally {
				O(!1);
			}
		}
	}
	async function z(e) {
		e && yo(e);
	}
	async function H(e) {
		if (e.id && window.confirm(`${ao(e)} 보고서를 삭제할까요?`)) {
			A(`delete-${e.id}`), M("");
			try {
				let t = await fetch(`/api/analysis-reports/${encodeURIComponent(e.id)}`, { method: "DELETE" });
				if (!t.ok) throw Error(`삭제 실패: ${t.status}`);
				r?.id === e.id && yo(), await L(), P("저장된 기업 분석 보고서를 삭제했습니다.");
			} catch (e) {
				M(e instanceof Error ? e.message : "보고서 삭제에 실패했습니다.");
			} finally {
				A("");
			}
		}
	}
	async function U(e) {
		if (r) {
			A(e), P(e === "notion" ? "Notion으로 내보내는 중..." : "Obsidian으로 내보내는 중...");
			try {
				let t = e === "notion" ? await V("/api/export-notion/analysis", r) : await V("/api/export-obsidian/analysis", r);
				P(e === "notion" ? `Notion으로 내보냈습니다${t.title ? `: ${t.title}` : ""}` : `Obsidian으로 내보냈습니다${t.company || t.filename ? `: ${t.company || t.filename}` : ""}`);
			} catch (e) {
				P(e instanceof Error ? e.message : "내보내기에 실패했습니다.");
			} finally {
				A("");
			}
		}
	}
	async function ee() {
		if (r?.id) {
			A("overlay"), P("내 노트와 연결하는 중...");
			try {
				let e = await V(`/api/analysis-reports/${encodeURIComponent(r.id)}/personal-overlay`, {});
				no(e) && await ro(e);
				let t = await B(`/api/analysis-reports/${encodeURIComponent(r.id)}?includePersonal=true`);
				i(t), P("내 노트와 연결했습니다.");
			} catch (e) {
				P(e instanceof Error ? e.message : "내 노트 연결에 실패했습니다.");
			} finally {
				A("");
			}
		}
	}
	let te = (0, l.useMemo)(() => {
		let e = ho(x);
		return e ? t.filter((t) => ho([
			X(t),
			io(t),
			ao(t),
			t.headline,
			t.mode,
			t.generatedAt,
			so(t.generatedAt)
		].filter(Boolean).join(" ")).includes(e)) : t;
	}, [x, t]), W = (0, l.useMemo)(() => {
		let e = [...te].sort((e, t) => String(t.generatedAt || "").localeCompare(String(e.generatedAt || "")));
		if (C === "recent") return e.length ? [{
			key: "recent",
			label: `최근 보고서 ${Math.min(e.length, eo)}건`,
			rows: e.slice(0, eo)
		}] : [];
		if (C === "month") {
			let t = /* @__PURE__ */ new Map();
			for (let n of e) {
				let e = mo(n.generatedAt);
				t.has(e) || t.set(e, []), t.get(e)?.push(n);
			}
			return Array.from(t.entries()).map(([e, t]) => ({
				key: e,
				label: e,
				rows: t
			}));
		}
		let t = /* @__PURE__ */ new Map();
		for (let n of e) {
			let e = X(n) || oo(n);
			t.has(e) || t.set(e, []), t.get(e)?.push(n);
		}
		return Array.from(t.entries()).map(([e, t]) => ({
			key: e,
			label: oo(t[0] || {}),
			rows: t.sort((e, t) => String(t.generatedAt || "").localeCompare(String(e.generatedAt || "")))
		})).sort((e, t) => String(t.rows[0]?.generatedAt || "").localeCompare(String(e.rows[0]?.generatedAt || "")));
	}, [te, C]), G = vo(r || {}), q = Y(G, r?.headline || ao(r || {})), ne = r?.sources || [], re = po(r);
	return r ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-company-analysis-route",
		"data-company-analysis-route": !0,
		children: [j && /* @__PURE__ */ (0, K.jsx)("p", {
			className: "react-dashboard-error",
			children: j
		}), /* @__PURE__ */ (0, K.jsxs)(Yn, {
			eyebrow: `COMPANY ANALYSIS${X(r) ? ` · ${X(r)}` : ""}`,
			title: q.title,
			meta: [r.generatedAt ? `생성일 ${so(r.generatedAt)}` : "", co(r.analysisStyle)].filter(Boolean).join(" · "),
			agentContext: {
				surface: "analysis_reader",
				viewId: "analysis",
				reportKind: "company_analysis",
				reportId: r.id || "",
				ticker: X(r)
			},
			breadcrumb: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
				type: "button",
				onClick: () => yo(),
				children: "기업 분석"
			}), /* @__PURE__ */ (0, K.jsx)("span", { children: q.title })] }),
			onClose: () => yo(),
			actionSlot: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
				/* @__PURE__ */ (0, K.jsx)(bn, {
					title: "AI",
					children: /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "agent",
						onClick: () => nt({
							surface: "analysis_reader",
							reportKind: "company_analysis",
							reportId: r.id || "",
							ticker: X(r),
							message: `${q.title}에서 투자 판단에 중요한 핵심, 리스크, 추가 확인 질문을 정리해줘.`,
							autoSubmit: !0
						}),
						children: "Agent에게 묻기"
					})
				}),
				/* @__PURE__ */ (0, K.jsx)(bn, {
					title: "노트",
					children: /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "link",
						disabled: k === "overlay" || !r.id,
						onClick: ee,
						children: k === "overlay" ? "연결 중" : "내 노트와 연결"
					})
				}),
				/* @__PURE__ */ (0, K.jsxs)(bn, {
					title: "내보내기",
					children: [/* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "notion",
						disabled: k === "notion",
						onClick: () => U("notion"),
						children: k === "notion" ? "내보내는 중" : "Notion으로 내보내기"
					}), /* @__PURE__ */ (0, K.jsx)(xn, {
						icon: "obsidian",
						disabled: k === "obsidian",
						onClick: () => U("obsidian"),
						children: k === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"
					})]
				}),
				re.length > 0 && /* @__PURE__ */ (0, K.jsx)(bn, {
					title: "자료 한계",
					children: /* @__PURE__ */ (0, K.jsx)("div", {
						className: "react-reader-gap-list",
						children: re.slice(0, 3).map((e, t) => /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "react-reader-gap",
							children: [
								/* @__PURE__ */ (0, K.jsx)("span", { children: lo(e.severity) }),
								/* @__PURE__ */ (0, K.jsx)("strong", { children: e.label || e.category || "추가 확인 필요" }),
								/* @__PURE__ */ (0, K.jsx)("p", { children: e.message || e.suggestedAction || "보고서 해석 시 확인이 필요한 자료 한계입니다." })
							]
						}, `${e.field || e.category || "gap"}-${t}`))
					})
				}),
				r.generation?.message && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "react-reader-status",
					children: r.generation.message
				}),
				N && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "react-reader-status",
					children: N
				})
			] }),
			noteIdentity: {
				id: qn("company", X(r) || r.headline || "company"),
				noteType: "company_thesis",
				title: X(r) ? `${X(r)} 투자 노트` : "기업 투자 노트",
				ticker: X(r),
				company: r.company?.name || "",
				label: X(r),
				reportKind: "company_analysis",
				reportId: X(r),
				linkedReports: [q.title].filter(Boolean)
			},
			noteLinkedTitle: q.title,
			noteOverlay: yr(r.personalOverlay, r.canonicalRevision),
			children: [/* @__PURE__ */ (0, K.jsx)(Na, {
				markdown: q.body || G,
				charts: r.analysisCharts
			}), ne.length > 0 && /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "source-panel react-analysis-sources",
				children: [/* @__PURE__ */ (0, K.jsx)("h4", { children: "참고자료" }), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "sources",
					children: ne.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "meta",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: go(e) }), e.url ? /* @__PURE__ */ (0, K.jsx)("a", {
							href: e.url,
							target: "_blank",
							rel: "noopener noreferrer",
							children: _o(e)
						}) : /* @__PURE__ */ (0, K.jsx)("span", { children: _o(e) })]
					}, `${_o(e)}-${t}`))
				})]
			})]
		})]
	}) : /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-company-analysis-route",
		"data-company-analysis-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Company Analysis",
				title: "기업 분석",
				description: "SEC, DART, 시장 데이터와 로컬 자료를 활용해 기업 분석 보고서를 생성합니다.",
				actions: /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: L,
					disabled: T,
					children: T ? "불러오는 중" : "새로고침"
				})
			}),
			/* @__PURE__ */ (0, K.jsxs)("form", {
				className: "react-analysis-form",
				onSubmit: R,
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "react-analysis-api-note",
						role: "note",
						children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "API 연동 안내" }), /* @__PURE__ */ (0, K.jsx)("span", { children: "미국 기업은 SEC 자료를 우선 사용하고, 한국 기업은 DART API Key를 설정하면 공시 확인 정확도가 높아집니다." })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "react-analysis-query",
						children: [/* @__PURE__ */ (0, K.jsxs)("label", {
							className: "portfolio-ticker-field",
							children: [
								/* @__PURE__ */ (0, K.jsx)("span", { children: "분석 대상" }),
								/* @__PURE__ */ (0, K.jsx)("input", {
									value: s,
									onChange: (e) => c(e.currentTarget.value),
									placeholder: "예: NVDA, 삼성전자, SK하이닉스",
									"aria-describedby": "analysis-resolution",
									autoComplete: "off"
								}),
								u?.status === "ambiguous" && u.candidates.length > 0 && !f && /* @__PURE__ */ (0, K.jsx)("div", {
									className: "ticker-suggest",
									role: "listbox",
									"aria-label": "후보 기업",
									children: u.candidates.map((e) => /* @__PURE__ */ (0, K.jsxs)("button", {
										type: "button",
										role: "option",
										"aria-selected": !1,
										onClick: () => p(e),
										children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.ticker }), /* @__PURE__ */ (0, K.jsx)("span", { children: e.name })]
									}, `${e.market}:${e.ticker}`))
								})
							]
						}), /* @__PURE__ */ (0, K.jsx)("p", {
							className: "analysis-resolution",
							id: "analysis-resolution",
							"data-status": _,
							children: v
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("fieldset", {
						className: "react-analysis-style",
						"aria-label": "보고서 모드",
						children: [/* @__PURE__ */ (0, K.jsx)("legend", { children: "보고서 모드" }), /* @__PURE__ */ (0, K.jsx)("div", {
							className: "segment react-analysis-style-toggle",
							"data-style": y,
							children: $a.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"aria-pressed": y === e.value,
								onClick: () => b(e.value),
								"data-tooltip": e.description,
								children: e.label
							}, e.value))
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "submit",
						disabled: D || !s.trim(),
						children: D ? "분석 중" : "분석"
					})
				]
			}),
			j && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: j
			}),
			N && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				children: N
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "find-bar",
				"aria-label": "저장 기업 분석 검색",
				children: [
					/* @__PURE__ */ (0, K.jsx)("input", {
						className: "find-bar__search",
						type: "search",
						value: x,
						onChange: (e) => S(e.currentTarget.value),
						placeholder: "티커·회사명·보고서 검색",
						"aria-label": "저장 기업 분석 검색"
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "보기" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "기업 분석 보기 방식",
							value: C,
							onChange: (e) => w(e.currentTarget.value),
							children: [
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "recent",
									children: "최근"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "company",
									children: "기업별"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "month",
									children: "월별"
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--text find-bar__reset",
						type: "button",
						onClick: () => {
							S(""), w("recent");
						},
						children: "초기화"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "react-analysis-feed",
				"aria-label": "저장된 기업 분석",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-section-heading",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "Saved Reports"
					}), /* @__PURE__ */ (0, K.jsx)("h2", { children: "저장된 기업 분석" })] }), /* @__PURE__ */ (0, K.jsx)("span", {
						"aria-live": "polite",
						children: T ? "불러오는 중..." : `${te.length}건${x ? " · 검색 결과" : ""}`
					})]
				}), W.length ? W.map((e) => /* @__PURE__ */ (0, K.jsxs)("section", {
					className: "report-feed-group",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-feed-group-head",
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-name",
							children: e.label
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-meta",
							children: hn(e.rows.length, e.rows[0]?.generatedAt)
						})]
					}), /* @__PURE__ */ (0, K.jsx)("div", {
						className: "report-feed-group-cards",
						children: e.rows.map((e) => {
							let t = k === `delete-${e.id}`;
							return /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "report-feed-card-wrap",
								children: [/* @__PURE__ */ (0, K.jsxs)("button", {
									className: "report-feed-card is-analysis",
									type: "button",
									onClick: () => z(e.id),
									children: [
										/* @__PURE__ */ (0, K.jsxs)("span", {
											className: "report-feed-card-meta",
											children: [(e.engine || e.mode) && /* @__PURE__ */ (0, K.jsxs)("span", {
												className: "report-feed-badge",
												children: [e.engine || String(e.mode).toUpperCase(), gn(e.engine, e.engineDetail) && /* @__PURE__ */ (0, K.jsx)("em", { children: gn(e.engine, e.engineDetail) })]
											}), e.analysisStyle && /* @__PURE__ */ (0, K.jsx)("span", {
												className: "report-feed-badge",
												children: co(e.analysisStyle) || String(e.analysisStyle).toUpperCase()
											})]
										}),
										/* @__PURE__ */ (0, K.jsx)("strong", { children: oo(e) }),
										/* @__PURE__ */ (0, K.jsxs)("span", {
											className: "report-feed-card-foot",
											children: ["생성일 ", so(e.generatedAt)]
										})
									]
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									className: "btn btn--icon report-feed-card-delete",
									disabled: t,
									onClick: () => H(e),
									"aria-label": `${ao(e)} 삭제`,
									"data-tooltip": "삭제",
									"data-tooltip-pos": "bottom",
									children: /* @__PURE__ */ (0, K.jsx)("svg", {
										width: "13",
										height: "13",
										viewBox: "0 0 16 16",
										fill: "none",
										stroke: "currentColor",
										strokeWidth: "1.4",
										strokeLinecap: "round",
										strokeLinejoin: "round",
										"aria-hidden": "true",
										children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" })
									})
								})]
							}, e.id || `${oo(e)}-${e.generatedAt}`);
						})
					})]
				}, e.key)) : /* @__PURE__ */ (0, K.jsxs)("article", {
					className: "react-dashboard-panel",
					children: [/* @__PURE__ */ (0, K.jsx)("h2", { children: "저장된 기업 분석 보고서가 없습니다." }), /* @__PURE__ */ (0, K.jsx)("p", { children: "분석 대상을 입력해 첫 보고서를 생성하세요." })]
				})]
			})
		]
	});
}
//#endregion
//#region src/app/dashboard/MarketCalendar.tsx
var Co = {
	macro: "경제지표",
	central_bank: "중앙은행",
	holiday: "휴장",
	earnings: "실적",
	filing: "공시",
	dividend: "배당"
}, wo = {
	confirmed: "확정",
	estimated: "추정",
	tentative: "미정",
	actual: "발표됨"
}, To = [
	{
		value: "earnings",
		label: "실적"
	},
	{
		value: "macro",
		label: "지표"
	},
	{
		value: "central_bank",
		label: "중앙은행"
	},
	{
		value: "holiday",
		label: "휴장"
	},
	{
		value: "filing",
		label: "공시"
	},
	{
		value: "dividend",
		label: "배당"
	}
], Eo = (e) => {
	let t = String(e ?? "").replace(/,/g, "").trim();
	if (!t) return null;
	let n = Number(t);
	return Number.isFinite(n) ? n : null;
};
function Do(e) {
	let t = Eo(e.actualValue), n = Eo(e.forecastValue);
	if (t !== null && n !== null) {
		let r = t - n, i = r > 0 ? "+" : "";
		return `예상 ${e.forecastValue} 대비 ${i}${Number(r.toFixed(4))}`;
	}
	return e.previousValue ? `직전 ${e.previousValue}` : "";
}
function Oo(e) {
	let t = Eo(e.actualValue), n = Eo(e.forecastValue) ?? Eo(e.previousValue);
	return t === null || n === null || t === n ? "flat" : t > n ? "up" : "down";
}
function ko(e) {
	let t = (e.tickers || [])[0], n = String(e.companyName || "").trim();
	return !t || !n || e.title.includes(n) ? e.title : e.title.replace(t, `${n} (${t})`);
}
var Ao = f, jo = [
	"US",
	"KR",
	"EUROPE",
	"JP"
], Mo = [
	{
		value: 3,
		label: "최상위",
		hint: "FOMC·금리 결정 같은 최상위 일정만"
	},
	{
		value: 2,
		label: "중간 이상",
		hint: "실적·주요 지표까지"
	},
	{
		value: 1,
		label: "전부",
		hint: "휴장일·배당까지 전부"
	}
], No = {
	nyse: "NYSE",
	krx: "KRX",
	lse: "런던",
	xetra: "프랑크푸르트",
	euronext: "파리·암스테르담",
	borsa_italiana: "밀라노",
	bme: "마드리드",
	jpx: "도쿄"
}, Po = [
	"월",
	"화",
	"수",
	"목",
	"금",
	"토",
	"일"
], Fo = 864e5;
function Io(e) {
	return `${e.getFullYear()}-${String(e.getMonth() + 1).padStart(2, "0")}-${String(e.getDate()).padStart(2, "0")}`;
}
function Lo() {
	let [e, t, n] = new Intl.DateTimeFormat("sv-SE", {
		timeZone: "Asia/Seoul",
		year: "numeric",
		month: "2-digit",
		day: "2-digit"
	}).format(/* @__PURE__ */ new Date()).split("-").map(Number);
	return new Date(e, t - 1, n);
}
function Ro(e) {
	if (e.allDay || /^\d{4}-\d{2}-\d{2}$/.test(e.startsAt)) return e.startsAt.slice(0, 10);
	let t = new Date(e.startsAt);
	return Number.isNaN(t.getTime()) ? e.startsAt.slice(0, 10) : new Intl.DateTimeFormat("sv-SE", {
		timeZone: "Asia/Seoul",
		year: "numeric",
		month: "2-digit",
		day: "2-digit"
	}).format(t);
}
function zo(e) {
	if (e.allDay || /^\d{4}-\d{2}-\d{2}$/.test(e.startsAt)) return "종일";
	let t = new Date(e.startsAt);
	if (Number.isNaN(t.getTime())) return "—";
	if (e.kind === "earnings") {
		let e = new Intl.DateTimeFormat("en-GB", {
			timeZone: "America/New_York",
			hour: "2-digit",
			minute: "2-digit",
			hour12: !1
		}).format(t);
		if (e === "00:00") return "발표일";
		if (e < "09:30") return "장전";
		if (e >= "16:00") return "장후";
	}
	return new Intl.DateTimeFormat("ko-KR", {
		timeZone: "Asia/Seoul",
		hour: "2-digit",
		minute: "2-digit",
		hour12: !1
	}).format(t);
}
function Bo(e, t) {
	return new Date(e.getFullYear(), e.getMonth(), e.getDate() + t);
}
function Vo(e) {
	let t = new Date(e.getFullYear(), e.getMonth(), e.getDate());
	return Bo(t, -((t.getDay() + 6) % 7));
}
function Ho(e) {
	if (e.kind === "earnings" && e.tickers?.length) return `${e.tickers[0]} · ${zo(e)}`;
	if (e.kind === "holiday") {
		let t = No[e.provider || ""];
		return t ? `휴장 · ${t}` : e.title.slice(0, 22);
	}
	return e.title.slice(0, 22);
}
function Uo({ focusSymbols: e }) {
	let [t, n] = (0, l.useState)([]), [r, i] = (0, l.useState)("week"), [a, o] = (0, l.useState)([]), [s, c] = (0, l.useState)([]), [u, f] = (0, l.useState)(1), { isSelected: p } = vn(), [m, h] = (0, l.useState)(!1), [g, _] = (0, l.useState)(() => Lo()), [v, y] = (0, l.useState)(() => Io(Lo())), [b, x] = (0, l.useState)(!1), [S, C] = (0, l.useState)(""), [w, T] = (0, l.useState)(""), E = (0, l.useCallback)(async () => {
		let e = /* @__PURE__ */ new Date(g.getTime() - 40 * Fo), t = new Date(g.getTime() + 70 * Fo);
		try {
			let r = await B(`/api/market-calendar?start=${encodeURIComponent(e.toISOString())}&end=${encodeURIComponent(t.toISOString())}&limit=500`);
			n(r.events || []), T("");
		} catch (e) {
			T(e instanceof Error ? e.message : "일정을 불러오지 못했습니다.");
		}
	}, [g]);
	(0, l.useEffect)(() => {
		E();
	}, [E]), (0, l.useEffect)(() => {
		B("/api/dashboard/settings").then((e) => {
			(e.calendarView === "week" || e.calendarView === "month") && i(e.calendarView), o(e.calendarKinds || (e.calendarKind && e.calendarKind !== "all" ? [e.calendarKind] : [])), c(e.calendarMarkets || (e.calendarMarket && e.calendarMarket !== "all" ? [e.calendarMarket] : [])), h(!!e.calendarWatchlistOnly), f(Math.min(Math.max(Number(e.calendarMinImportance) || 1, 1), 3));
		}).catch(() => void 0);
	}, []);
	function D(e) {
		V("/api/dashboard/settings", e).catch(() => void 0);
	}
	let O = (0, l.useMemo)(() => new Set(e.filter((e) => e.source !== "fallback").map((e) => e.symbol.toUpperCase())), [e]), k = (0, l.useMemo)(() => t.filter((e) => !(a.length && !a.includes(e.kind) || !p(e.market || "") || (e.importance || 1) < u || s.length && !s.includes((e.market || "").toUpperCase()) || m && !(e.tickers || []).some((e) => O.has(e.toUpperCase())))), [
		t,
		a,
		s,
		m,
		O,
		p,
		u
	]), A = (0, l.useMemo)(() => {
		let e = /* @__PURE__ */ new Map();
		for (let t of k) {
			let n = Ro(t);
			e.set(n, [...e.get(n) || [], t]);
		}
		for (let t of e.values()) t.sort((e, t) => (t.importance || 0) - (e.importance || 0) || e.startsAt.localeCompare(t.startsAt));
		return e;
	}, [k]), j = Vo(g), M = Array.from({ length: 7 }, (e, t) => Bo(j, t)), N = new Date(g.getFullYear(), g.getMonth(), 1), P = (0, l.useMemo)(() => {
		let e = Vo(N), t = [];
		for (let n = 0; n < 42; n += 1) t.push(Bo(e, n));
		for (; t.length > 7 && t[t.length - 7].getMonth() !== g.getMonth();) t.splice(-7, 7);
		return t;
	}, [g, N]), F = Io(Lo()), I = A.get(v) || [], L = (/* @__PURE__ */ new Date(`${v}T00:00:00`)).toLocaleDateString("ko-KR", {
		month: "long",
		day: "numeric",
		weekday: "long"
	}), R = (0, l.useMemo)(() => {
		let e = /* @__PURE__ */ new Map();
		for (let t of I) e.set(t.kind, (e.get(t.kind) || 0) + 1);
		return [...e.entries()].map(([e, t]) => `${Co[e] || e} ${t}`).join(" · ");
	}, [I]);
	function z(e) {
		_(r === "week" ? (t) => Bo(t, e * 7) : (t) => new Date(t.getFullYear(), t.getMonth() + e, 1));
	}
	async function H() {
		x(!0), C(""), T("");
		try {
			let e = await V("/api/market-calendar/refresh", {}), t = e.providers?.fred_macro;
			C(`일정 ${e.stored ?? 0}건 수집${t === "fred_key_required" ? " · 미국 지표 일정은 설정에서 FRED API Key를 등록하면 함께 수집됩니다" : ""}`), await E();
		} catch (e) {
			T(e instanceof Error ? e.message : "일정 수집에 실패했습니다.");
		} finally {
			x(!1);
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "cockpit-panel cockpit-calendar",
		"aria-labelledby": "market-calendar-title",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cockpit-panel__head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "MARKET CALENDAR" }), /* @__PURE__ */ (0, K.jsx)("h2", {
					id: "market-calendar-title",
					children: "주요 실적·지표 일정"
				})] }), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "cockpit-panel__actions",
					children: [
						/* @__PURE__ */ (0, K.jsx)("div", {
							className: "cockpit-chart-controls",
							children: /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "segment",
								role: "group",
								"aria-label": "캘린더 보기",
								children: [/* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									"aria-pressed": r === "week",
									onClick: () => {
										i("week"), D({ calendarView: "week" });
									},
									children: "주간"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									"aria-pressed": r === "month",
									onClick: () => {
										i("month"), D({ calendarView: "month" });
									},
									children: "월간"
								})]
							})
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--icon",
							type: "button",
							"aria-label": r === "week" ? "이전 주" : "이전 달",
							onClick: () => z(-1),
							children: "◀"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							onClick: () => {
								let e = Lo();
								_(e), y(Io(e));
							},
							children: "오늘"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--icon",
							type: "button",
							"aria-label": r === "week" ? "다음 주" : "다음 달",
							onClick: () => z(1),
							children: "▶"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							onClick: H,
							disabled: b,
							children: b ? "수집 중" : "일정 수집"
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cal-filter-row",
				role: "group",
				"aria-label": "일정 유형 필터",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					className: "cal-filter-label",
					children: "유형"
				}), To.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "cal-filter",
					"aria-pressed": a.includes(e.value),
					onClick: () => {
						let t = a.includes(e.value) ? a.filter((t) => t !== e.value) : [...a, e.value];
						o(t), D({ calendarKinds: t });
					},
					children: e.label
				}, e.value))]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cal-filter-row",
				role: "group",
				"aria-label": "일정 시장 필터",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "cal-filter-label",
						children: "시장"
					}),
					jo.filter((e) => p(e)).map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "cal-filter",
						"aria-pressed": s.includes(e),
						onClick: () => {
							let t = s.includes(e) ? s.filter((t) => t !== e) : [...s, e];
							c(t), D({ calendarMarkets: t });
						},
						children: d[e] || e
					}, e)),
					/* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "cal-filter cal-watch-toggle",
						"aria-pressed": m,
						onClick: () => {
							let e = !m;
							h(e), D({ calendarWatchlistOnly: e });
						},
						children: "보유·관심만"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cal-filter-row",
				role: "group",
				"aria-label": "일정 중요도 필터",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					className: "cal-filter-label",
					children: "중요도"
				}), Mo.map((e) => /* @__PURE__ */ (0, K.jsxs)("button", {
					type: "button",
					className: "cal-filter cal-imp-filter",
					"aria-pressed": u === e.value,
					"data-tooltip": e.hint,
					onClick: () => {
						f(e.value), D({ calendarMinImportance: e.value });
					},
					children: [/* @__PURE__ */ (0, K.jsx)("span", {
						className: "imp",
						"aria-hidden": "true",
						children: [
							1,
							2,
							3
						].map((t) => /* @__PURE__ */ (0, K.jsx)("u", { className: t <= e.value ? "on" : "" }, t))
					}), e.label]
				}, e.value))]
			}),
			S && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-reader-status",
				children: S
			}),
			w && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				role: "alert",
				children: w
			}),
			r === "week" ? /* @__PURE__ */ (0, K.jsx)("div", {
				className: "cal-week-strip",
				role: "tablist",
				"aria-label": "이번 주",
				children: M.map((e, t) => {
					let n = Io(e), r = A.get(n) || [], i = [...new Set(r.map((e) => e.kind))].slice(0, 3);
					return /* @__PURE__ */ (0, K.jsxs)("button", {
						type: "button",
						role: "tab",
						"aria-selected": n === v,
						className: `cal-day${n === v ? " cal-day--active" : ""}${t >= 5 ? " cal-day--dim" : ""}${n === F ? " cal-day--today" : ""}`,
						onClick: () => y(n),
						children: [
							/* @__PURE__ */ (0, K.jsxs)("span", { children: [Po[t], n === F ? " · 오늘" : ""] }),
							/* @__PURE__ */ (0, K.jsxs)("b", { children: [
								e.getMonth() + 1,
								".",
								e.getDate()
							] }),
							/* @__PURE__ */ (0, K.jsx)("small", { children: r.length ? `${r.length}건` : "—" }),
							/* @__PURE__ */ (0, K.jsx)("i", { children: i.map((e) => /* @__PURE__ */ (0, K.jsx)("u", { "data-kind": e }, e)) })
						]
					}, n);
				})
			}) : /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cal-month-grid",
				"aria-label": `${g.getFullYear()}년 ${g.getMonth() + 1}월`,
				children: [Po.map((e, t) => /* @__PURE__ */ (0, K.jsx)("span", {
					className: `cal-dow${t >= 5 ? " cal-dow--dim" : ""}`,
					children: e
				}, e)), P.map((e) => {
					let t = Io(e), n = A.get(t) || [], r = e.getMonth() !== g.getMonth();
					return /* @__PURE__ */ (0, K.jsxs)("button", {
						type: "button",
						"aria-pressed": t === v,
						className: `cal-cell${t === F ? " cal-cell--today" : ""}${r ? " cal-cell--dim" : ""}${t === v ? " cal-cell--active" : ""}`,
						onClick: () => y(t),
						children: [
							/* @__PURE__ */ (0, K.jsxs)("header", { children: [
								e.getDate(),
								n.length ? /* @__PURE__ */ (0, K.jsxs)("b", { children: [n.length, "건"] }) : null,
								t === F ? /* @__PURE__ */ (0, K.jsx)("i", { children: "오늘" }) : null
							] }),
							n.slice(0, 3).map((e) => /* @__PURE__ */ (0, K.jsx)("span", {
								className: "ev",
								"data-kind": e.kind,
								children: Ho(e)
							}, e.id)),
							n.length > 3 ? /* @__PURE__ */ (0, K.jsxs)("em", { children: [
								"+",
								n.length - 3,
								"건"
							] }) : null
						]
					}, t);
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("p", {
				className: "cal-day-head",
				children: [/* @__PURE__ */ (0, K.jsx)("b", { children: L }), I.length ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
					" · ",
					I.length,
					"건 — ",
					R
				] }) : null]
			}),
			I.length ? /* @__PURE__ */ (0, K.jsx)("div", {
				className: "table-scroll",
				children: /* @__PURE__ */ (0, K.jsxs)("table", {
					className: "cal-table",
					children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "시간(KST)"
						}),
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "시장"
						}),
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "중요도"
						}),
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "이벤트"
						}),
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "결과"
						}),
						/* @__PURE__ */ (0, K.jsx)("th", {
							scope: "col",
							children: "확정도"
						})
					] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: I.map((e) => /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, K.jsx)("td", { children: zo(e) }),
						/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("span", {
							className: "chip mkt-chip",
							children: Ao[e.market || ""] || e.market || "—"
						}) }),
						/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("span", {
							className: "imp",
							"aria-label": `중요도 ${e.importance || 1}/3`,
							children: [
								1,
								2,
								3
							].map((t) => /* @__PURE__ */ (0, K.jsx)("u", { className: (e.importance || 1) >= t ? "on" : "" }, t))
						}) }),
						/* @__PURE__ */ (0, K.jsxs)("td", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: ko(e) }), /* @__PURE__ */ (0, K.jsxs)("small", { children: [
							Co[e.kind] || e.kind,
							e.source ? ` · ${e.source}` : "",
							e.sourceUrl ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [" · ", /* @__PURE__ */ (0, K.jsx)("a", {
								href: e.sourceUrl,
								target: "_blank",
								rel: "noopener noreferrer",
								children: "원문"
							})] }) : null
						] })] }),
						/* @__PURE__ */ (0, K.jsx)("td", {
							className: "cal-actual",
							children: e.actualValue ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
								/* @__PURE__ */ (0, K.jsxs)("b", { children: [e.actualValue, e.unit ? ` ${e.unit}` : ""] }),
								Do(e) ? /* @__PURE__ */ (0, K.jsx)("small", {
									"data-direction": Oo(e),
									children: Do(e)
								}) : null,
								e.observedAt ? /* @__PURE__ */ (0, K.jsxs)("small", { children: [e.observedAt, " 기준"] }) : null
							] }) : /* @__PURE__ */ (0, K.jsx)("span", {
								className: "cal-actual__pending",
								children: "—"
							})
						}),
						/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("span", {
							className: `chip certainty-badge--${e.status}`,
							children: wo[e.status] || e.status
						}) })
					] }, e.id)) })]
				})
			}) : /* @__PURE__ */ (0, K.jsx)("p", {
				className: "cockpit-empty",
				children: t.length ? "이 날짜에는 표시할 일정이 없습니다." : "저장된 시장 일정이 없습니다. 위의 일정 수집을 실행하면 미국·한국·유럽·일본 휴장일, FOMC·ECB·BoE·BOJ 금리 결정, 보유/관심 종목 실적이 채워집니다."
			})
		]
	});
}
//#endregion
//#region src/app/dashboard/MarketChartFigure.tsx
var Wo = {
	snapshot: "스냅샷",
	current: "최신",
	fresh: "최신",
	cached: "최근 조회",
	delayed: "지연",
	stale: "오래됨",
	unavailable: "불러올 수 없음"
}, Go = [
	"1d",
	"1m",
	"3m",
	"1y",
	"5y"
], Ko = {
	"1d": "1D",
	"1m": "1M",
	"3m": "3M",
	"1y": "1Y",
	"5y": "5Y"
}, qo = (e) => e === "1d" ? "5m" : "1d";
function Jo(e) {
	return e.startsWith("^") || e.includes("=");
}
function Yo(e) {
	let t = String(e || "").match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
	if (!t) return NaN;
	let n = Date.UTC(Number(t[1]), Number(t[2]) - 1, Number(t[3]), Number(t[4]), Number(t[5]), Number(t[6] || 0));
	return Number.isFinite(n) ? Math.floor(n / 1e3) : NaN;
}
function Xo(e, t) {
	if (!t) return String(e || "");
	let n = Yo(e);
	return Number.isFinite(n) ? n : String(e || "");
}
function Zo(e) {
	let t = new Date(e.startsAt), n = Number.isNaN(t.getTime()) ? e.startsAt.slice(0, 10) : t.toLocaleDateString("ko-KR", {
		timeZone: "Asia/Seoul",
		month: "numeric",
		day: "numeric",
		weekday: "short"
	}), r = Co[e.kind] || e.kind, i = e.kind === "earnings" ? zo(e) : "";
	return `${n} ${r} 예정${i && i !== "종일" ? ` · ${i}` : ""}`;
}
function Qo({ symbol: e, label: t, range: n, style: r, onRange: i, onStyle: a, showEvent: o = !0 }) {
	let [s, c] = (0, l.useState)(null), [u, d] = (0, l.useState)(null), [f, p] = (0, l.useState)(""), m = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		let t = !0;
		return p(""), c((t) => t && t.symbol === e ? t : null), B(`/api/market/chart?symbol=${encodeURIComponent(e)}&range=${n}&interval=${qo(n)}`).then((e) => {
			t && c(e);
		}).catch((e) => {
			t && p(e instanceof Error ? e.message : "차트를 불러오지 못했습니다.");
		}), () => {
			t = !1;
		};
	}, [e, n]), (0, l.useEffect)(() => {
		let t = !0;
		if (d(null), !o || !e || Jo(e)) return;
		let n = /* @__PURE__ */ new Date(), r = new Date(n.getTime() + 7776e6);
		return B(`/api/market-calendar?start=${encodeURIComponent(n.toISOString())}&end=${encodeURIComponent(r.toISOString())}&ticker=${encodeURIComponent(e)}&limit=20`).then((e) => {
			if (!t) return;
			let n = (e.events || []).filter((e) => [
				"earnings",
				"dividend",
				"filing"
			].includes(e.kind)).sort((e, t) => e.startsAt.localeCompare(t.startsAt));
			d(n[0] || null);
		}).catch(() => void 0), () => {
			t = !1;
		};
	}, [e, o]);
	let [h, g] = (0, l.useState)(0);
	(0, l.useEffect)(() => {
		let e = new MutationObserver(() => g((e) => e + 1));
		return e.observe(document.documentElement, {
			attributes: !0,
			attributeFilter: ["data-theme"]
		}), () => e.disconnect();
	}, []), (0, l.useEffect)(() => {
		let e = m.current, t = window.LightweightCharts;
		if (!e || !t || !s?.series?.length) return;
		e.innerHTML = "";
		let n = getComputedStyle(document.documentElement), i = (e, t) => n.getPropertyValue(e).trim() || t, a = i("--folio-green", "#3b6d11"), o = i("--folio-burgundy", "#8a1024"), c = s.series, l = s.interval === "5m", u = !(c.length > 1) || c[c.length - 1].close >= c[0].close ? a : o, d = t.createChart(e, {
			autoSize: !0,
			height: 360,
			width: e.clientWidth || 0,
			layout: {
				background: {
					type: "solid",
					color: i("--folio-surface-clean", "#ffffff")
				},
				textColor: i("--folio-ink-muted", "#44505f"),
				attributionLogo: !0
			},
			grid: {
				vertLines: { visible: !1 },
				horzLines: {
					color: i("--folio-border", "#dde2e9"),
					style: t.LineStyle?.Dotted ?? 1
				}
			},
			rightPriceScale: {
				borderVisible: !1,
				scaleMargins: {
					top: .12,
					bottom: .08
				}
			},
			timeScale: {
				borderVisible: !1,
				rightOffset: 1,
				barSpacing: 8,
				minBarSpacing: 2,
				timeVisible: l,
				secondsVisible: !1
			},
			localization: {
				locale: "ko-KR",
				dateFormat: "yyyy-MM-dd"
			},
			crosshair: { mode: t.CrosshairMode?.Normal ?? 0 },
			handleScroll: {
				mouseWheel: !1,
				pressedMouseMove: !0,
				horzTouchDrag: !0,
				vertTouchDrag: !1
			},
			handleScale: {
				axisPressedMouseMove: !1,
				mouseWheel: !1,
				pinch: !0
			}
		}), f = c.filter((e) => e.open != null && e.high != null && e.low != null), p = r === "candle" && f.length > 0, h = p ? d.addSeries(t.CandlestickSeries, {
			upColor: a,
			downColor: o,
			wickUpColor: a,
			wickDownColor: o,
			borderVisible: !1
		}) : d.addSeries(t.AreaSeries, {
			lineColor: u,
			topColor: `${u}38`,
			bottomColor: `${u}05`,
			lineWidth: 3,
			priceLineVisible: !1,
			lastValueVisible: !0
		});
		h.setData(p ? f.map((e) => ({
			time: Xo(e.time, l),
			open: e.open,
			high: e.high,
			low: e.low,
			close: e.close
		})) : c.map((e) => ({
			time: Xo(e.time, l),
			value: e.close
		})));
		let g = new Map(c.map((e, t) => [String(Xo(e.time, l)), {
			close: e.close,
			previous: t > 0 ? c[t - 1].close : null
		}])), _ = document.createElement("div");
		return _.className = "market-chart-tooltip", _.hidden = !0, e.appendChild(_), d.subscribeCrosshairMove((t) => {
			let n = t?.point, r = t?.seriesData?.get(h), i = e.getBoundingClientRect();
			if (!n || !r || n.x < 0 || n.y < 0 || n.x > i.width || n.y > i.height) {
				_.hidden = !0;
				return;
			}
			let a = String(r.time), o = g.get(a), s = o?.close ?? r.close ?? r.value ?? null, c = o?.previous ?? null, u = s != null && c != null ? s - c : null, d = u != null && c ? u / c * 100 : null, f = u == null || u >= 0 ? "up" : "down", p = s == null ? "가격 없음" : s.toLocaleString(void 0, { maximumFractionDigits: 2 }), m = u == null || d == null ? l ? "직전 봉 대비 없음" : "전일 대비 없음" : `${u >= 0 ? "+" : ""}${u.toLocaleString(void 0, { maximumFractionDigits: 2 })} (${d >= 0 ? "+" : ""}${d.toFixed(2)}%)`;
			_.innerHTML = "";
			let v = document.createElement("div");
			v.className = "market-chart-tooltip__date", v.textContent = l ? (/* @__PURE__ */ new Date(Number(a) * 1e3)).toISOString().slice(11, 16) : a;
			let y = document.createElement("div");
			y.className = "market-chart-tooltip__price", y.textContent = p;
			let b = document.createElement("div");
			b.className = "market-chart-tooltip__change", b.dataset.direction = f, b.textContent = m, _.append(v, y, b);
			let x = _.offsetWidth || 150, S = _.offsetHeight || 76, C = Math.min(Math.max(8, n.x + 14), Math.max(8, i.width - x - 8)), w = Math.min(Math.max(8, n.y - S - 12), Math.max(8, i.height - S - 8));
			_.style.transform = `translate(${C}px, ${w}px)`, _.hidden = !1;
		}), d.timeScale().fitContent(), () => d.remove();
	}, [
		s,
		h,
		r
	]);
	let _ = s?.series || [], v = _.length ? _[_.length - 1].close : null, y = s?.interval === "5m", b = _.length > 1 ? y ? _[0].close : _[_.length - 2].close : null, x = v != null && b ? (v - b) / b * 100 : null, S = Wo[s?.freshness || ""] || (s ? s.freshness : "불러오는 중");
	return /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
		/* @__PURE__ */ (0, K.jsxs)("div", {
			className: "chart-headline",
			children: [/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "chart-quote",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "chart-quote__name",
						children: t || e
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "chart-quote__value",
						children: [v == null ? null : /* @__PURE__ */ (0, K.jsx)("b", { children: v.toLocaleString(void 0, { maximumFractionDigits: 2 }) }), x == null ? null : /* @__PURE__ */ (0, K.jsxs)("span", {
							className: x > 0 ? "up" : x < 0 ? "down" : "flat",
							children: [
								x > 0 ? "▲" : x < 0 ? "▼" : "—",
								" ",
								x > 0 ? "+" : "",
								x.toFixed(1),
								"%"
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("small", { children: [S, s?.asOf ? ` · ${s.asOf} 기준` : ""] })
				]
			}), /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cockpit-chart-controls",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "segment",
					role: "group",
					"aria-label": "차트 유형",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						"aria-pressed": r === "line",
						onClick: () => a("line"),
						children: "라인"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						"aria-pressed": r === "candle",
						onClick: () => a("candle"),
						children: "캔들"
					})]
				}), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "segment",
					role: "group",
					"aria-label": "차트 기간",
					children: Go.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						"aria-pressed": n === e,
						onClick: () => i(e),
						children: Ko[e] || e
					}, e))
				})]
			})]
		}),
		f && /* @__PURE__ */ (0, K.jsx)("p", {
			className: "react-dashboard-error",
			children: f
		}),
		/* @__PURE__ */ (0, K.jsx)("div", {
			className: "cockpit-chart-stage",
			ref: m,
			children: !window.LightweightCharts && /* @__PURE__ */ (0, K.jsx)("p", { children: "차트 라이브러리를 사용할 수 없습니다." })
		}),
		o && u && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "chart-next",
			children: [
				/* @__PURE__ */ (0, K.jsx)("span", {
					className: `chip certainty-badge--${u.status}`,
					children: wo[u.status] || u.status
				}),
				"다음 일정 — ",
				/* @__PURE__ */ (0, K.jsx)("b", { children: Zo(u) }),
				/* @__PURE__ */ (0, K.jsx)("small", { children: "시장 캘린더 연동" })
			]
		}),
		s?.notice ? /* @__PURE__ */ (0, K.jsx)("div", {
			className: "cockpit-chart-foot",
			children: /* @__PURE__ */ (0, K.jsx)("small", { children: s.notice })
		}) : null
	] });
}
//#endregion
//#region src/app/dashboard/NativeMarketChart.tsx
var $o = [
	{
		symbol: "^GSPC",
		label: "S&P 500"
	},
	{
		symbol: "^IXIC",
		label: "NASDAQ"
	},
	{
		symbol: "^DJI",
		label: "DOW"
	},
	{
		symbol: "^KS11",
		label: "KOSPI"
	},
	{
		symbol: "^KQ11",
		label: "KOSDAQ"
	},
	{
		symbol: "KRW=X",
		label: "USD/KRW"
	}
];
function es({ symbols: e }) {
	let t = e.filter((e) => e.source !== "fallback" && !$o.some((t) => t.symbol === e.symbol)), [n, r] = (0, l.useState)(""), [i, a] = (0, l.useState)(""), [o, s] = (0, l.useState)($o[0].symbol), [c, u] = (0, l.useState)("3m"), [d, f] = (0, l.useState)("line"), p = (0, l.useRef)(!1);
	async function m(e) {
		await V("/api/watchlist", { items: e }), document.dispatchEvent(new CustomEvent("folio:generation-complete"));
	}
	async function h() {
		let e = n.trim().toUpperCase();
		if (e) {
			a("");
			try {
				let t = await B("/api/watchlist");
				if (t.some((t) => t.toUpperCase() === e)) {
					a("이미 관심 종목에 있습니다.");
					return;
				}
				await m([...t, e]), r("");
			} catch (e) {
				a(e instanceof Error ? e.message : "추가하지 못했습니다.");
			}
		}
	}
	async function g(t) {
		a("");
		try {
			let n = await B("/api/watchlist"), r = (e.find((e) => e.symbol === t)?.label || "").toLowerCase(), i = n.filter((e) => {
				let n = e.trim().toLowerCase();
				return n !== t.toLowerCase() && (!r || n !== r);
			});
			if (i.length === n.length) {
				a("워치리스트에서 해당 항목을 찾지 못했습니다.");
				return;
			}
			await m(i);
		} catch (e) {
			a(e instanceof Error ? e.message : "제거하지 못했습니다.");
		}
	}
	(0, l.useEffect)(() => {
		p.current || (p.current = !0, B("/api/dashboard/settings").then((e) => {
			e.chartRange && Go.includes(e.chartRange) && u(e.chartRange), e.chartSymbol && s(e.chartSymbol), (e.chartStyle === "line" || e.chartStyle === "candle") && f(e.chartStyle);
		}).catch(() => void 0));
	}, []), (0, l.useEffect)(() => {
		$o.some((e) => e.symbol === o) || t.some((e) => e.symbol === o) || s($o[0].symbol);
	}, [t, o]);
	function _(e) {
		s(e), V("/api/dashboard/settings", { chartSymbol: e }).catch(() => void 0);
	}
	function v(e) {
		u(e), V("/api/dashboard/settings", { chartRange: e }).catch(() => void 0);
	}
	function y(e) {
		f(e), V("/api/dashboard/settings", { chartStyle: e }).catch(() => void 0);
	}
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "cockpit-panel cockpit-chart",
		"aria-labelledby": "native-chart-title",
		children: [/* @__PURE__ */ (0, K.jsxs)("div", {
			className: "cockpit-panel__head",
			children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "MARKET CHART" }), /* @__PURE__ */ (0, K.jsx)("h2", {
				id: "native-chart-title",
				children: "시장 차트"
			})] }), /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "chart-pickers",
				children: [/* @__PURE__ */ (0, K.jsxs)("details", {
					className: "chart-picker",
					children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "지수" }), /* @__PURE__ */ (0, K.jsx)("div", {
						className: "chart-picker__list",
						children: $o.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							className: `sym-chip${e.symbol === o ? " sym-chip--active" : ""}`,
							"aria-pressed": e.symbol === o,
							onClick: () => _(e.symbol),
							children: e.label
						}, e.symbol))
					})]
				}), /* @__PURE__ */ (0, K.jsxs)("details", {
					className: "chart-picker",
					children: [/* @__PURE__ */ (0, K.jsxs)("summary", { children: ["관심 종목", t.length ? ` ${t.length}` : ""] }), /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "chart-picker__list",
						children: [
							t.map((e) => /* @__PURE__ */ (0, K.jsxs)("span", {
								className: "chart-picker__row",
								children: [/* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									title: e.label || e.symbol,
									className: `sym-chip${e.symbol === o ? " sym-chip--active" : ""}`,
									"aria-pressed": e.symbol === o,
									onClick: () => _(e.symbol),
									children: e.symbol
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									className: "btn btn--icon chart-picker__remove",
									"aria-label": `${e.label || e.symbol} 관심 종목에서 제거`,
									onClick: () => void g(e.symbol),
									children: "×"
								})]
							}, e.symbol)),
							/* @__PURE__ */ (0, K.jsxs)("form", {
								className: "chart-picker__add",
								onSubmit: (e) => {
									e.preventDefault(), h();
								},
								children: [/* @__PURE__ */ (0, K.jsx)("input", {
									value: n,
									onChange: (e) => r(e.currentTarget.value),
									placeholder: "티커 추가",
									"aria-label": "관심 종목 추가"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn btn--sm",
									type: "submit",
									disabled: !n.trim(),
									children: "추가"
								})]
							}),
							i && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "chart-picker__error",
								children: i
							})
						]
					})]
				})]
			})]
		}), /* @__PURE__ */ (0, K.jsx)(Qo, {
			symbol: o,
			label: $o.find((e) => e.symbol === o)?.label || o,
			range: c,
			style: d,
			onRange: v,
			onStyle: y
		})]
	});
}
//#endregion
//#region src/app/dashboard/ResearchCockpit.tsx
function ts() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)(""), i = (0, l.useCallback)(() => B("/api/dashboard/cockpit").then(t).catch((e) => r(e instanceof Error ? e.message : "대시보드를 불러오지 못했습니다.")), []);
	if ((0, l.useEffect)(() => {
		i();
		let e = () => i();
		return document.addEventListener("folio:generation-complete", e), () => document.removeEventListener("folio:generation-complete", e);
	}, [i]), n) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "react-dashboard-error",
		children: n
	});
	if (!e) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "section-subtitle",
		children: "대시보드를 불러오는 중입니다."
	});
	let a = e.changeCounts || {}, o = (e.providerHealth || []).filter((e) => ["stale", "unhealthy"].includes(String(e.sourceStatus || ""))), s = e.focusSymbols || [];
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "research-cockpit",
		"data-invalidation-token": e.invalidationToken,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cockpit-summary",
				role: "status",
				"aria-label": "오늘의 변화 요약",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "chip cockpit-summary__chip",
						"data-tone": "burgundy",
						children: ["중대한 변화 ", a.majorChange || 0]
					}),
					/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "chip cockpit-summary__chip",
						"data-tone": "blue",
						children: ["발전 중 ", a.developingSignal || 0]
					}),
					/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "chip cockpit-summary__chip",
						"data-tone": "gold",
						children: ["충돌·불확실 ", a.conflictingUncertain || 0]
					}),
					/* @__PURE__ */ (0, K.jsxs)("span", {
						className: "chip cockpit-summary__chip",
						"data-tone": "muted",
						children: ["그 외 평가 ", a.quiet || 0]
					}),
					o.map((e) => /* @__PURE__ */ (0, K.jsxs)("span", {
						className: "chip cockpit-summary__chip",
						"data-tone": "burgundy",
						children: [e.provider, " 수집 문제"]
					}, e.provider))
				]
			}),
			/* @__PURE__ */ (0, K.jsx)(li, { events: e.changes || [] }),
			/* @__PURE__ */ (0, K.jsx)(Uo, { focusSymbols: s }),
			/* @__PURE__ */ (0, K.jsx)(es, { symbols: s })
		]
	});
}
//#endregion
//#region src/app/Dashboard.tsx
function ns() {
	return (0, l.useEffect)(() => {
		Qe("dashboard", {
			surface: "dashboard",
			viewId: "dashboard",
			reportKind: "",
			reportId: ""
		});
	}, []), /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-dashboard",
		"data-react-dashboard": !0,
		"data-dashboard-mode": "cockpit",
		children: [/* @__PURE__ */ (0, K.jsx)(Xn, {
			eyebrow: "Research Cockpit",
			title: "대시보드",
			description: "새 보고서에서 확인된 변화, 집중 차트, 시장 일정을 한 화면에서 점검합니다."
		}), /* @__PURE__ */ (0, K.jsx)(ts, {})]
	});
}
//#endregion
//#region src/app/marketStateContext.ts
var rs = [
	"current",
	"stale",
	"empty",
	"fallback"
];
function is(e) {
	return typeof e == "object" && e && !Array.isArray(e) ? e : null;
}
function as(e, t) {
	return Object.prototype.hasOwnProperty.call(e, t);
}
function os(e) {
	return typeof e == "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(e) && Number.isFinite(new Date(e).getTime());
}
function ss(e) {
	return typeof e == "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(e) && Number.isFinite(new Date(e).getTime());
}
var cs = /* @__PURE__ */ new Set([
	"invalid_as_of",
	"future_as_of",
	"missing_input_watermark",
	"age_exceeded",
	"new_relevant_evidence",
	"update_failed"
]);
function ls(e) {
	let t = is(e), n = is(t?.marketStateRef) || is(is(t?.marketStateResolution)?.ref) || is(t?.ref);
	if (!n || !rs.includes(n.status) || [
		"snapshotId",
		"sourceKind",
		"scope",
		"asOf",
		"status",
		"freshnessReason",
		"inputWatermark",
		"relevantEvidenceWatermark",
		"invalidWatermarkRows",
		"resolvedAt",
		"layer"
	].some((e) => !as(n, e))) return null;
	let r = n.sourceKind, i = n.scope;
	if (![
		"snapshot",
		"state_fallback",
		"none"
	].includes(r) || ![
		"GLOBAL",
		"US",
		"KR"
	].includes(i) || n.layer !== "source-grounded" || !os(n.resolvedAt) || !Number.isInteger(n.invalidWatermarkRows) || Number(n.invalidWatermarkRows) < 0 || n.inputWatermark !== null && typeof n.inputWatermark != "string" || n.relevantEvidenceWatermark !== null && typeof n.relevantEvidenceWatermark != "string" || n.relevantEvidenceWatermark !== null && !os(n.relevantEvidenceWatermark)) return null;
	let a = n.status, o = n.freshnessReason;
	return typeof o != "string" || a === "current" && (r !== "snapshot" || typeof n.snapshotId != "string" || !n.snapshotId || !ss(n.asOf) || o !== "within_window") || a === "current" && n.inputWatermark !== null && !os(n.inputWatermark) || a === "current" && n.inputWatermark === null != (n.relevantEvidenceWatermark === null) || a === "stale" && (r !== "snapshot" || typeof n.snapshotId != "string" || !n.snapshotId || !cs.has(o)) || a === "stale" && o !== "invalid_as_of" && !ss(n.asOf) || a === "fallback" && (r !== "state_fallback" || n.snapshotId !== null || n.asOf !== null && !ss(n.asOf) || o !== "state_fallback" || n.inputWatermark !== null) || a === "empty" && (r !== "none" || n.snapshotId !== null || n.asOf !== null || o !== "no_state" || n.inputWatermark !== null || n.relevantEvidenceWatermark !== null) ? null : {
		snapshotId: typeof n.snapshotId == "string" ? n.snapshotId : null,
		sourceKind: r,
		scope: i,
		asOf: typeof n.asOf == "string" ? n.asOf : null,
		status: a,
		freshnessReason: o,
		inputWatermark: typeof n.inputWatermark == "string" ? n.inputWatermark : null,
		relevantEvidenceWatermark: typeof n.relevantEvidenceWatermark == "string" ? n.relevantEvidenceWatermark : null,
		invalidWatermarkRows: Number.isFinite(Number(n.invalidWatermarkRows)) ? Number(n.invalidWatermarkRows) : 0,
		resolvedAt: n.resolvedAt,
		layer: "source-grounded"
	};
}
function us(e) {
	let t = ls(e);
	return t ? {
		status: t.status,
		asOf: t.asOf,
		freshnessReason: t.freshnessReason,
		sourceKind: t.sourceKind,
		scope: t.scope,
		resolvedAt: t.resolvedAt
	} : null;
}
//#endregion
//#region src/app/SmartCollectionEditor.tsx
var ds = {
	name: "",
	query: "",
	market: "ALL",
	sources: "",
	tickers: "",
	tags: ""
};
function fs(e, t = !1) {
	let n = e.split(",").map((e) => e.normalize("NFKC").trim()).filter(Boolean).map((e) => t ? e.toUpperCase() : e.toLowerCase());
	return Array.from(new Set(n)).sort();
}
function ps(e) {
	return {
		name: e.name.normalize("NFKC").trim(),
		query: e.query.normalize("NFKC").trim(),
		market: e.market,
		sources: fs(e.sources),
		tickers: fs(e.tickers, !0),
		tags: fs(e.tags)
	};
}
function ms(e) {
	return {
		name: e.name,
		query: e.query,
		market: e.market,
		sources: e.sources.join(", "),
		tickers: e.tickers.join(", "),
		tags: e.tags.join(", ")
	};
}
function hs({ mode: e, revision: t, draft: n, busy: r, onChange: i, onCancel: a, onSave: o }) {
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "topicrpt-collection-editor",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collection-subhead",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e === "create" ? "새 검색 규칙" : "검색 규칙 편집" }), /* @__PURE__ */ (0, K.jsx)("span", { children: t ? `revision ${t}` : "새 정의" })]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collection-form-grid",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "이름" }), /* @__PURE__ */ (0, K.jsx)("input", {
							"data-qa": "collection-name",
							value: n.name,
							maxLength: 80,
							onChange: (e) => i("name", e.currentTarget.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field topicrpt-collection-query",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "검색어" }), /* @__PURE__ */ (0, K.jsx)("textarea", {
							"data-qa": "collection-query",
							value: n.query,
							maxLength: 500,
							rows: 2,
							onChange: (e) => i("query", e.currentTarget.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"data-qa": "collection-market",
							value: n.market,
							onChange: (e) => i("market", e.currentTarget.value),
							children: [
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "ALL",
									children: "전체"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "US",
									children: "미국"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "KR",
									children: "한국"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "GLOBAL",
									children: "글로벌"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "UNKNOWN",
									children: "미분류"
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "출처 · 쉼표 구분" }), /* @__PURE__ */ (0, K.jsx)("input", {
							"data-qa": "collection-sources",
							value: n.sources,
							onChange: (e) => i("sources", e.currentTarget.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "티커 · 쉼표 구분" }), /* @__PURE__ */ (0, K.jsx)("input", {
							"data-qa": "collection-tickers",
							value: n.tickers,
							onChange: (e) => i("tickers", e.currentTarget.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "태그 · 쉼표 구분" }), /* @__PURE__ */ (0, K.jsx)("input", {
							"data-qa": "collection-tags",
							value: n.tags,
							onChange: (e) => i("tags", e.currentTarget.value)
						})]
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collections-actions",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					"data-qa": "collection-cancel",
					disabled: r,
					onClick: a,
					children: "취소"
				}), /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn btn--primary",
					type: "button",
					"data-qa": "collection-save",
					disabled: r,
					onClick: o,
					children: r ? "저장 중" : e === "create" ? "컬렉션 저장" : "변경 저장"
				})]
			})
		]
	});
}
//#endregion
//#region src/app/SmartCollectionWorkspace.tsx
function gs(e) {
	return [
		e.query && `query: ${e.query}`,
		e.market !== "ALL" && `market: ${e.market}`,
		e.sources.length && `sources: ${e.sources.join(", ")}`,
		e.tickers.length && `tickers: ${e.tickers.join(", ")}`,
		e.tags.length && `tags: ${e.tags.join(", ")}`
	].filter(Boolean).join(" · ") || "필터 없음";
}
function _s(e) {
	return e instanceof F ? e.code === "validation_error" ? "필터 형식을 확인하세요. 이름과 하나 이상의 검색 조건이 필요하며 각 목록은 최대 20개입니다." : e.code === "collection_store_unavailable" ? "저장된 컬렉션을 읽을 수 없습니다. 저장소 상태를 확인한 뒤 다시 불러오세요." : e.code === "collection_snapshot_unavailable" ? "최근 새로고침 기록을 읽을 수 없습니다. 저장 상태를 확인한 뒤 다시 시도하세요." : e.code === "collection_source_unavailable" ? "현재 외부 자료 인덱스를 읽을 수 없습니다. 자료 상태를 확인한 뒤 다시 시도하세요." : e.code === "collection_not_found" ? "컬렉션이 더 이상 존재하지 않습니다. 목록으로 돌아가세요." : `컬렉션 요청을 완료하지 못했습니다 (${e.code || "request_failed"}).` : "컬렉션 요청을 완료하지 못했습니다. 연결을 확인하고 다시 시도하세요.";
}
function vs(e) {
	let t = e.payload?.currentRevision;
	return typeof t == "number" && Number.isInteger(t) && t >= 1 ? t : null;
}
function ys(e) {
	if (!e) return "아직 새로고침하지 않음";
	let t = e.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
	return t ? `${t[1]} ${t[2]} UTC` : e;
}
function bs(e) {
	return {
		baseline_missing: "비교할 이전 스냅샷 없음",
		definition_changed: "필터 정의 변경",
		empty_index: "현재 일치 자료 없음",
		high_unusable_ratio: "사용 불가 자료 비율 높음",
		high_churn_ratio: "자료 교체 비율 높음",
		invalid_resolved_at: "새로고침 시각 확인 필요",
		clock_skew: "시스템 시각 불일치",
		snapshot_expired: "최근 스냅샷 만료",
		provider_generation_reset: "자료 제공자 세대 초기화",
		provider_watermark_reset: "자료 워터마크 초기화",
		result_truncated: "표시 상한 적용",
		healthy: "현재 입력 정상"
	}[e] || e;
}
function xs({ selectedRef: e, onSelectedRef: t, onBusyChange: n, onOpenDetail: r, disabled: i }) {
	let [a, o] = (0, l.useState)([]), [s, c] = (0, l.useState)(0), [u, d] = (0, l.useState)(!0), [f, p] = (0, l.useState)(null), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(null), [v, y] = (0, l.useState)(ds), [b, x] = (0, l.useState)(null), [S, C] = (0, l.useState)(!1), [w, T] = (0, l.useState)(!1), [E, D] = (0, l.useState)(""), [O, k] = (0, l.useState)(null), A = (0, l.useRef)(0), j = (0, l.useRef)(0), M = (0, l.useRef)(null), N = (0, l.useRef)(null);
	function P(e, t) {
		y((n) => ({
			...n,
			[e]: t
		}));
	}
	let I = (0, l.useMemo)(() => e && a.find((t) => t.id === e.id && t.revision === e.revision) || null, [a, e]);
	(0, l.useEffect)(() => {
		n(u || S || w);
	}, [
		w,
		u,
		n,
		S
	]);
	let L = (0, l.useCallback)(async (n = !1) => {
		M.current?.abort();
		let r = new AbortController();
		M.current = r;
		let i = A.current + 1;
		A.current = i, d(!0), D("");
		try {
			let a = await B("/api/smart-collections?limit=100&offset=0", { signal: r.signal });
			if (r.signal.aborted || i !== A.current) return;
			if (o(a.items), c(a.total), e) {
				let n = a.items.find((t) => t.id === e.id);
				(!n || n.revision !== e.revision) && (t(null), x(null), n && k({
					code: "revision_conflict",
					currentRevision: n.revision
				}));
			}
			if (n && m) {
				let e = a.items.find((e) => e.id === m);
				e && (_(e.revision), k(null));
			}
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || i !== A.current) return;
			D(_s(e));
		} finally {
			!r.signal.aborted && i === A.current && d(!1);
		}
	}, [
		m,
		t,
		e
	]), R = (0, l.useCallback)(async (e) => {
		N.current?.abort();
		let n = new AbortController();
		N.current = n;
		let r = j.current + 1;
		j.current = r, C(!0), x(null), t(null), D(""), k(null);
		let i = {
			expectedRevision: e.revision,
			limit: 10
		};
		try {
			let a = await V(`/api/smart-collections/${encodeURIComponent(e.id)}/preview`, i, { signal: n.signal });
			if (n.signal.aborted || r !== j.current) return;
			x(a), t({
				id: e.id,
				revision: e.revision
			});
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || r !== j.current) return;
			e instanceof F && e.status === 409 && (e.code === "revision_conflict" || e.code === "duplicate_name") ? (k({
				code: e.code,
				currentRevision: vs(e)
			}), t(null)) : D(_s(e));
		} finally {
			!n.signal.aborted && r === j.current && C(!1);
		}
	}, [t]);
	(0, l.useEffect)(() => (L(), () => {
		M.current?.abort(), N.current?.abort();
	}), []);
	let z = () => {
		p("create"), h(""), _(null), y(ds), k(null), D("");
	}, H = () => {
		I && (p("edit"), h(I.id), _(I.revision), y(ms(I)), k(null), D(""));
	}, U = async () => {
		let e = ps(v);
		if (!e.name || !e.query && e.market === "ALL" && !e.sources.length && !e.tickers.length && !e.tags.length || e.sources.length > 20 || e.tickers.length > 20 || e.tags.length > 20) {
			D("이름과 하나 이상의 검색 조건을 입력하세요. 쉼표 목록은 각각 최대 20개입니다.");
			return;
		}
		T(!0), D(""), k(null);
		try {
			let t;
			if (f === "edit" && m && g) {
				let n = {
					...e,
					expectedRevision: g
				};
				t = await te(`/api/smart-collections/${encodeURIComponent(m)}`, n);
			} else t = await V("/api/smart-collections", e);
			o((e) => [t.collection, ...e.filter((e) => e.id !== t.collection.id)]), c((e) => f === "create" ? e + 1 : e), p(null), h(""), _(null), await R(t.collection);
		} catch (e) {
			e instanceof F && e.status === 409 && (e.code === "revision_conflict" || e.code === "duplicate_name") ? (k({
				code: e.code,
				currentRevision: vs(e)
			}), e.code === "revision_conflict" && t(null)) : D(_s(e));
		} finally {
			T(!1);
		}
	}, ee = async () => {
		if (!I || !window.confirm(`“${I.name}” 컬렉션을 삭제할까요?`)) return;
		T(!0), D(""), k(null);
		let e = { expectedRevision: I.revision };
		try {
			await W(`/api/smart-collections/${encodeURIComponent(I.id)}`, e), o((e) => e.filter((e) => e.id !== I.id)), c((e) => Math.max(0, e - 1)), x(null), t(null);
		} catch (e) {
			e instanceof F && e.status === 409 && (e.code === "revision_conflict" || e.code === "duplicate_name") ? (k({
				code: e.code,
				currentRevision: vs(e)
			}), t(null)) : D(_s(e));
		} finally {
			T(!1);
		}
	};
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-collections-panel",
		"data-qa": "collection-panel",
		"aria-labelledby": "collection-heading",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collections-head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "section-kicker",
						children: "Smart Collections"
					}),
					/* @__PURE__ */ (0, K.jsxs)("h3", {
						id: "collection-heading",
						children: ["저장한 자료 모음 사용 ", /* @__PURE__ */ (0, K.jsx)("em", { children: "(선택)" })]
					}),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "미리 저장해 둔 검색 규칙으로 자료 범위를 좁힙니다. 근거 자체가 아니며, 계획 시점에 일치하는 자료를 다시 확인합니다." })
				] }), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "topicrpt-collections-actions",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						"data-qa": "collection-reload",
						disabled: u || w || i,
						onClick: () => void L(),
						children: u ? "불러오는 중" : "다시 불러오기"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "button",
						"data-qa": "collection-new",
						disabled: w || i,
						onClick: z,
						children: "새 컬렉션"
					})]
				})]
			}),
			E && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-dashboard-error topicrpt-collection-alert",
				"data-qa": "collection-error",
				role: "alert",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "컬렉션을 확인하세요" }), /* @__PURE__ */ (0, K.jsx)("span", { children: E })]
			}),
			O && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-dashboard-warning topicrpt-collection-alert",
				"data-qa": "collection-conflict",
				role: "alert",
				children: [
					/* @__PURE__ */ (0, K.jsx)("strong", { children: O.code === "duplicate_name" ? "같은 이름이 이미 있습니다" : "다른 탭에서 정의가 변경되었습니다" }),
					/* @__PURE__ */ (0, K.jsxs)("span", { children: [O.currentRevision ? `현재 버전 ${O.currentRevision}. ` : "", "입력 내용은 유지했습니다. 최신 버전을 불러온 뒤 다시 저장하세요."] }),
					O.code === "duplicate_name" ? /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => k(null),
						children: "이름 수정"
					}) : /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => void L(!0),
						children: "최신 버전 불러오기"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collections-grid",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "topicrpt-collection-browser",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "topicrpt-collection-subhead",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "저장된 규칙" }), /* @__PURE__ */ (0, K.jsxs)("span", { children: [s, "개"] })]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "topicrpt-collection-list",
							"data-qa": "collection-list",
							"aria-busy": u,
							children: [!u && !E && !a.length && /* @__PURE__ */ (0, K.jsx)("div", {
								className: "topicrpt-collection-empty",
								"data-qa": "collection-empty",
								"data-empty-kind": "list",
								role: "status",
								children: "저장한 자료 모음이 없습니다. 새 컬렉션을 만들어 반복해 쓸 검색 범위를 저장하세요."
							}), a.map((t) => {
								let n = e?.id === t.id && e.revision === t.revision;
								return /* @__PURE__ */ (0, K.jsxs)("button", {
									className: `topicrpt-collection-item${n ? " is-selected" : ""}`,
									type: "button",
									"data-qa": "collection-item",
									"data-collection-id": t.id,
									"data-revision": t.revision,
									"aria-pressed": n,
									disabled: w || i,
									onClick: () => void R(t),
									children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: t.name }), /* @__PURE__ */ (0, K.jsxs)("small", { children: ["버전 ", t.revision] })] }), /* @__PURE__ */ (0, K.jsx)("small", { children: gs(t) })]
								}, t.id);
							})]
						}),
						s > a.length && /* @__PURE__ */ (0, K.jsxs)("p", {
							className: "topicrpt-collection-disclosure",
							children: [
								"처음 ",
								a.length,
								"개를 표시합니다. 전체 ",
								s,
								"개 중 나머지는 API 페이지에서 확인할 수 있습니다."
							]
						}),
						I && /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "topicrpt-collections-actions topicrpt-selection-actions",
							children: [
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									"data-qa": "collection-open-workspace",
									disabled: w || i,
									onClick: () => r(I.id),
									children: "상세 워크스페이스"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									"data-qa": "collection-edit",
									disabled: w || i,
									onClick: H,
									children: "선택 규칙 편집"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									"data-qa": "collection-delete",
									disabled: w || i,
									onClick: () => void ee(),
									children: "삭제"
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									"data-qa": "collection-clear-selection",
									onClick: () => {
										N.current?.abort(), x(null), t(null);
									},
									children: "선택 해제"
								})
							]
						})
					]
				}), /* @__PURE__ */ (0, K.jsxs)("section", {
					className: "topicrpt-collection-results",
					"data-qa": "collection-results",
					"aria-busy": S,
					"aria-live": "polite",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "topicrpt-collection-subhead",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "현재 일치 자료" }), /* @__PURE__ */ (0, K.jsx)("span", { children: S ? "확인 중" : b ? `${b.total}건` : "규칙 선택 전" })]
						}),
						b && b.total === 0 && /* @__PURE__ */ (0, K.jsx)("div", {
							className: "topicrpt-collection-empty",
							"data-qa": "collection-empty",
							"data-empty-kind": "matches",
							role: "status",
							children: "현재 일치 자료가 0건입니다. 계획은 근거 부족 확인을 거쳐야 하며, 이 컬렉션 자체가 근거로 사용되지는 않습니다."
						}),
						b && b.items.length > 0 && /* @__PURE__ */ (0, K.jsx)("ul", {
							className: "topicrpt-collection-samples",
							children: b.items.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [
								/* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.title || "제목 없음" }), /* @__PURE__ */ (0, K.jsx)("em", {
									className: e.usability === "indexed" ? "is-indexed" : "is-unindexed",
									children: e.usability === "indexed" ? "사용 가능" : "인덱싱 필요"
								})] }),
								/* @__PURE__ */ (0, K.jsx)("small", { children: [e.source, e.publishedAt].filter(Boolean).join(" · ") || "출처 정보 없음" }),
								e.snippet && /* @__PURE__ */ (0, K.jsx)("p", { children: e.snippet })
							] }, e.id))
						}),
						!b && !S && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "topicrpt-empty-value",
							children: "규칙을 선택하면 서버가 현재 자료의 개수와 표본을 확인합니다."
						}),
						b && b.total > b.items.length && /* @__PURE__ */ (0, K.jsxs)("p", {
							className: "topicrpt-collection-disclosure",
							children: [
								"상위 ",
								b.items.length,
								"건만 미리 표시합니다. 계획 실행 시 서버가 전체 범위를 다시 해석합니다."
							]
						})
					]
				})]
			}),
			f && /* @__PURE__ */ (0, K.jsx)(hs, {
				mode: f,
				revision: g,
				draft: v,
				busy: w,
				onChange: P,
				onCancel: () => {
					p(null), k(null), D("");
				},
				onSave: () => void U()
			})
		]
	});
}
function Ss({ collectionId: e, onBack: t, onStartResearch: n }) {
	let [r, i] = (0, l.useState)(null), [a, o] = (0, l.useState)(null), [s, c] = (0, l.useState)(!0), [u, d] = (0, l.useState)(!1), [f, p] = (0, l.useState)(null), [m, h] = (0, l.useState)(""), g = (0, l.useRef)(null), _ = (0, l.useCallback)(async ({ preserveMessage: t = !1 } = {}) => {
		g.current?.abort();
		let n = new AbortController();
		g.current = n, c(!0), p(null), t || h("");
		try {
			let t = encodeURIComponent(e), [r, a] = await Promise.all([B(`/api/smart-collections/${t}/workspace`, { signal: n.signal }), B(`/api/smart-collections/${t}/changes`, { signal: n.signal })]);
			if (n.signal.aborted) return;
			i(r), o(a);
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") return;
			e instanceof F && e.code === "collection_not_found" ? p("deleted") : e instanceof F && e.code === "collection_source_unavailable" ? p("source") : p("other"), h(_s(e));
		} finally {
			n.signal.aborted || c(!1);
		}
	}, [e]);
	(0, l.useEffect)(() => (_(), () => g.current?.abort()), [_]);
	let v = async () => {
		if (!r) return;
		d(!0), h("");
		let t = { expectedRevision: r.collection.revision };
		try {
			await V(`/api/smart-collections/${encodeURIComponent(e)}/refresh`, t), await _();
		} catch (e) {
			e instanceof F && e.status === 409 ? (h("다른 탭에서 정의가 변경되었습니다. 최신 revision을 다시 불러왔습니다."), await _({ preserveMessage: !0 })) : e instanceof F && e.code === "collection_not_found" ? (p("deleted"), h(_s(e))) : (e instanceof F && e.code === "collection_source_unavailable" && p("source"), h(_s(e)));
		} finally {
			d(!1);
		}
	}, y = () => {
		r && nt({
			surface: "smart_collection_workspace",
			viewId: "topicrpt",
			collectionId: r.collection.id,
			collectionRevision: r.collection.revision,
			message: "이 Smart Collection의 현재 스냅샷과 이전 스냅샷을 비교해 무엇이 바뀌었는지 설명해줘. 추가·제외된 외부 근거와 불확실성을 함께 정리해줘.",
			autoSubmit: !0
		});
	};
	if (s && !r) return /* @__PURE__ */ (0, K.jsx)("section", {
		className: "topicrpt-collection-workspace",
		"data-qa": "collection-workspace",
		"aria-busy": "true",
		children: /* @__PURE__ */ (0, K.jsx)("p", {
			className: "react-dashboard-warning",
			children: "컬렉션과 현재 외부 자료를 확인하는 중입니다."
		})
	});
	if (f === "deleted") return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-collection-workspace",
		"data-qa": "collection-workspace",
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "btn",
			type: "button",
			"data-qa": "collection-workspace-back",
			onClick: t,
			children: "딥 리서치로 돌아가기"
		}), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "react-dashboard-warning",
			"data-qa": "collection-workspace-deleted",
			role: "status",
			children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "이 컬렉션은 삭제되었습니다" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "열려 있던 주소는 유지되지만 더 이상 새로고침하거나 리서치 범위로 사용할 수 없습니다." })]
		})]
	});
	if (f === "source") return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-collection-workspace",
		"data-qa": "collection-workspace",
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "btn",
			type: "button",
			"data-qa": "collection-workspace-back",
			onClick: t,
			children: "딥 리서치로 돌아가기"
		}), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "react-dashboard-error",
			"data-qa": "collection-workspace-source-unavailable",
			role: "alert",
			children: [
				/* @__PURE__ */ (0, K.jsx)("strong", { children: "현재 외부 자료를 읽을 수 없습니다" }),
				/* @__PURE__ */ (0, K.jsx)("p", { children: m }),
				/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: () => void _(),
					children: "다시 확인"
				})
			]
		})]
	});
	if (!r) return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-collection-workspace",
		"data-qa": "collection-workspace",
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "btn",
			type: "button",
			"data-qa": "collection-workspace-back",
			onClick: t,
			children: "딥 리서치로 돌아가기"
		}), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "react-dashboard-error",
			role: "alert",
			children: [
				/* @__PURE__ */ (0, K.jsx)("strong", { children: "컬렉션을 열지 못했습니다" }),
				/* @__PURE__ */ (0, K.jsx)("p", { children: m }),
				/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: () => void _(),
					children: "다시 확인"
				})
			]
		})]
	});
	let b = r.health;
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-collection-workspace",
		"data-qa": "collection-workspace",
		"data-health": b,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collection-workspace-head",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					"data-qa": "collection-workspace-back",
					onClick: t,
					children: "← 딥 리서치"
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "topicrpt-collections-actions",
					children: [
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							"data-qa": "collection-workspace-refresh",
							disabled: u,
							onClick: () => void v(),
							children: u ? "새로고침 중" : "현재 자료 새로고침"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							"data-qa": "collection-workspace-ask-change",
							onClick: y,
							children: "Agent에게 변화 묻기"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							"data-qa": "collection-workspace-start",
							onClick: () => n({
								id: r.collection.id,
								revision: r.collection.revision
							}),
							children: "이 범위로 리서치 시작"
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("header", {
				className: "topicrpt-collection-workspace-title",
				children: [
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "저장한 자료 모음"
					}),
					/* @__PURE__ */ (0, K.jsx)("h1", { children: r.collection.name }),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "저장된 검색 규칙이며 외부 근거 자체가 아닙니다. 새 리서치를 시작하면 이 규칙의 ID와 버전으로 자료를 다시 확인합니다." }),
					/* @__PURE__ */ (0, K.jsxs)("small", { children: [
						gs(r.collection),
						" · 버전 ",
						r.collection.revision
					] })
				]
			}),
			m && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				role: "status",
				children: m
			}),
			b === "empty" && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "topicrpt-collection-empty",
				"data-qa": "collection-workspace-empty",
				role: "status",
				children: "현재 일치하는 외부 자료가 없습니다. 범위를 조정하거나 자료 인덱스를 갱신하세요."
			}),
			b === "stale" && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "react-dashboard-warning",
				"data-qa": "collection-workspace-stale",
				role: "status",
				children: "최근 입력 상태가 오래되었거나 제공자 상태를 다시 확인해야 합니다."
			}),
			b === "noisy" && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "react-dashboard-warning",
				"data-qa": "collection-workspace-noisy",
				role: "status",
				children: "자료 교체 또는 사용 불가 비율이 높습니다. 변경 내역을 확인한 뒤 리서치를 시작하세요."
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collection-health-rail",
				"data-qa": "collection-workspace-health",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", { children: [
						/* @__PURE__ */ (0, K.jsx)("span", { children: "상태" }),
						/* @__PURE__ */ (0, K.jsx)("strong", { children: b }),
						/* @__PURE__ */ (0, K.jsx)("small", { children: r.healthReasonCodes.map(bs).join(" · ") })
					] }),
					/* @__PURE__ */ (0, K.jsxs)("div", { children: [
						/* @__PURE__ */ (0, K.jsx)("span", { children: "마지막 새로고침" }),
						/* @__PURE__ */ (0, K.jsx)("strong", { children: ys(r.lastRefresh) }),
						/* @__PURE__ */ (0, K.jsx)("small", { children: r.current.truncated ? "표시 상한 적용" : "현재 범위 확인" })
					] }),
					/* @__PURE__ */ (0, K.jsxs)("div", { children: [
						/* @__PURE__ */ (0, K.jsx)("span", { children: "변경" }),
						/* @__PURE__ */ (0, K.jsxs)("strong", { children: [
							"+",
							r.changeCounts.added,
							" / −",
							r.changeCounts.removed
						] }),
						/* @__PURE__ */ (0, K.jsxs)("small", { children: [
							"유지 ",
							r.changeCounts.unchanged,
							"건"
						] })
					] }),
					/* @__PURE__ */ (0, K.jsxs)("div", { children: [
						/* @__PURE__ */ (0, K.jsx)("span", { children: "현재 자료" }),
						/* @__PURE__ */ (0, K.jsxs)("strong", { children: [r.current.resolvedCount, "건"] }),
						/* @__PURE__ */ (0, K.jsxs)("small", { children: [
							"사용 제외 ",
							r.current.unusableCount,
							"건"
						] })
					] })
				]
			}),
			/* @__PURE__ */ (0, K.jsx)(ln, {
				mode: "collection",
				collectionId: r.collection.id
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-collection-workspace-grid",
				children: [/* @__PURE__ */ (0, K.jsxs)("section", {
					className: "topicrpt-collection-results",
					"data-qa": "collection-workspace-evidence",
					"aria-labelledby": "collection-current-evidence",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-collection-subhead",
						children: [/* @__PURE__ */ (0, K.jsx)("strong", {
							id: "collection-current-evidence",
							children: "현재 외부 자료"
						}), /* @__PURE__ */ (0, K.jsxs)("span", { children: [r.current.eligibleCount, "건 일치"] })]
					}), r.recentEvidence.length ? /* @__PURE__ */ (0, K.jsx)("ul", {
						className: "topicrpt-collection-samples",
						children: r.recentEvidence.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [
							/* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.title || "제목 없음" }), /* @__PURE__ */ (0, K.jsx)("em", {
								className: e.usability === "indexed" ? "is-indexed" : "is-unindexed",
								children: e.usability === "indexed" ? "사용 가능" : "인덱싱 필요"
							})] }),
							/* @__PURE__ */ (0, K.jsx)("small", { children: [e.source, e.publishedAt].filter(Boolean).join(" · ") || "출처 정보 없음" }),
							e.snippet && /* @__PURE__ */ (0, K.jsx)("p", { children: e.snippet }),
							e.url && /* @__PURE__ */ (0, K.jsx)("a", {
								href: e.url,
								target: "_blank",
								rel: "noopener noreferrer",
								children: "원문 열기"
							})
						] }, e.id))
					}) : /* @__PURE__ */ (0, K.jsx)("p", {
						className: "topicrpt-empty-value",
						children: "표시할 현재 외부 자료가 없습니다."
					})]
				}), /* @__PURE__ */ (0, K.jsxs)("aside", {
					className: "topicrpt-collection-change-ledger",
					"aria-labelledby": "collection-change-heading",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "topicrpt-collection-subhead",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", {
								id: "collection-change-heading",
								children: "스냅샷 변경"
							}), /* @__PURE__ */ (0, K.jsx)("span", { children: a?.observedAt ? ys(a.observedAt) : "확인 전" })]
						}),
						/* @__PURE__ */ (0, K.jsxs)("dl", { children: [
							/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "추가" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a?.counts.added ?? r.changeCounts.added })] }),
							/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "제외" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a?.counts.removed ?? r.changeCounts.removed })] }),
							/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "유지" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a?.counts.unchanged ?? r.changeCounts.unchanged })] }),
							/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "사용 불가" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: a?.counts.unusable ?? r.current.unusableCount })] })
						] }),
						a?.removedIds.length ? /* @__PURE__ */ (0, K.jsxs)("details", { children: [/* @__PURE__ */ (0, K.jsxs)("summary", { children: [
							"제외된 identity ",
							a.removedIds.length,
							"건"
						] }), /* @__PURE__ */ (0, K.jsx)("ul", { children: a.removedIds.map((e) => /* @__PURE__ */ (0, K.jsx)("li", { children: e }, e)) })] }) : null,
						/* @__PURE__ */ (0, K.jsx)("p", { children: "Collection 정의는 저장된 필터 메타데이터입니다. 위 자료 카드만 현재 외부 evidence 후보입니다." })
					]
				})]
			})
		]
	});
}
//#endregion
//#region src/app/DeepResearchRoute.tsx
var Cs = [{
	value: "auto",
	label: "AI",
	hint: "설정한 엔진이 이 질문에 맞는 축과 검색어를 씁니다. 40초쯤 걸립니다."
}, {
	value: "rules",
	label: "규칙",
	hint: "보고서 유형의 기본 축으로 즉시 만듭니다."
}];
function ws({ children: e = "저장된 구조화 정보가 없습니다." }) {
	return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "topicrpt-provenance-empty",
		children: e
	});
}
function Ts({ report: e }) {
	let t = e.topicPlan, n = e.evidencePackSummary, r = e.researchResolution, i = yr(e.personalOverlay, e.canonicalRevision), a = typeof e.userContext == "string" ? e.userContext.trim() : e.userContext ? "생성 요청에 사용자 컨텍스트가 포함되었습니다." : "";
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "topicrpt-provenance",
		"aria-labelledby": "dr-provenance-heading",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-provenance-heading",
				children: [
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "사용한 자료와 생성 과정"
					}),
					/* @__PURE__ */ (0, K.jsx)("h2", {
						id: "dr-provenance-heading",
						children: "리서치 근거 추적"
					}),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "승인한 계획, 외부 근거, 부족한 자료, 내 생각을 서로 구분해 보여줍니다." })
				]
			}),
			e.contractWarnings.length > 0 && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "topicrpt-contract-warning",
				role: "status",
				children: "일부 구조화 필드가 올바르지 않아 안전한 빈 상태로 표시했습니다."
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-provenance-grid",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel",
						"data-qa": "dr-approved-plan",
						"aria-labelledby": "dr-approved-plan-heading",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "dr-approved-plan-heading",
							children: "승인된 계획"
						}), t ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsxs)("dl", {
								className: "topicrpt-provenance-facts",
								children: [
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "주제" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.topic || "미기록" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "보고서 유형" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.reportType ? wr(t.reportType) : "미기록" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "사용자 의도" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.userIntent || "미기록" })] })
								]
							}),
							/* @__PURE__ */ (0, K.jsx)("h4", { children: "리서치 질문" }),
							Ys(t.researchQuestions),
							/* @__PURE__ */ (0, K.jsx)("h4", { children: "반증 조건" }),
							Ys(t.falsificationTriggers)
						] }) : /* @__PURE__ */ (0, K.jsx)(ws, {})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel",
						"data-qa": "dr-evidence-coverage",
						"aria-labelledby": "dr-evidence-coverage-heading",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "dr-evidence-coverage-heading",
							children: "근거 커버리지"
						}), n ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsxs)("dl", {
								className: "topicrpt-provenance-facts",
								children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "외부 문서" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [n.totalDocs, "건"] })] }), /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "메모리 참조" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [n.memoryCount, "건"] })] })]
							}),
							Object.keys(n.roleCounts).length > 0 && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("h4", { children: "근거 역할" }), /* @__PURE__ */ (0, K.jsx)("ul", {
								className: "topicrpt-provenance-list",
								children: Object.entries(n.roleCounts).map(([e, t]) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e }), /* @__PURE__ */ (0, K.jsxs)("span", { children: [t, "건"] })] }, e))
							})] }),
							Object.keys(n.axisCoverage).length ? /* @__PURE__ */ (0, K.jsx)("ul", {
								className: "topicrpt-provenance-list",
								children: Object.entries(n.axisCoverage).map(([e, t]) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: t.label || e }), /* @__PURE__ */ (0, K.jsxs)("span", { children: [
									t.count,
									"건 · ",
									t.level || "수준 미상"
								] })] }, e))
							}) : /* @__PURE__ */ (0, K.jsx)(ws, { children: "분석 축별 커버리지가 없습니다." }),
							Object.keys(n.questionCoverage).length > 0 && /* @__PURE__ */ (0, K.jsxs)("details", { children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "리서치 질문 커버리지" }), /* @__PURE__ */ (0, K.jsx)("ul", {
								className: "topicrpt-provenance-list",
								children: Object.entries(n.questionCoverage).map(([e, t]) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: t.question || e }), /* @__PURE__ */ (0, K.jsxs)("span", { children: [
									t.count,
									"건 · ",
									t.level || "수준 미상"
								] })] }, e))
							})] }),
							e.evidenceItems.length > 0 && /* @__PURE__ */ (0, K.jsxs)("details", { children: [/* @__PURE__ */ (0, K.jsxs)("summary", { children: [
								"선별된 근거 ",
								e.evidenceItems.length,
								"건"
							] }), /* @__PURE__ */ (0, K.jsx)("ul", {
								className: "topicrpt-provenance-list",
								children: e.evidenceItems.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.title }), /* @__PURE__ */ (0, K.jsx)("span", { children: [
									e.source,
									e.role,
									e.confidence
								].filter(Boolean).join(" · ") })] }, e.id))
							})] })
						] }) : /* @__PURE__ */ (0, K.jsx)(ws, {})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel topicrpt-provenance-wide",
						"data-qa": "dr-source-ledger",
						"aria-labelledby": "dr-source-ledger-heading",
						children: [
							/* @__PURE__ */ (0, K.jsx)("h3", {
								id: "dr-source-ledger-heading",
								children: "외부 근거 원장"
							}),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "topicrpt-layer-note",
								children: "이 목록만 보고서의 권위 있는 외부 출처 원장입니다."
							}),
							e.sourceLedger.length ? /* @__PURE__ */ (0, K.jsx)("ol", {
								className: "topicrpt-source-ledger",
								children: e.sourceLedger.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.title || "제목 미상" }), /* @__PURE__ */ (0, K.jsx)("span", { children: [
										e.source,
										e.date,
										e.evidenceRole,
										e.reliability,
										e.artifactType
									].filter(Boolean).join(" · ") })] }),
									e.usedInSections.length > 0 && /* @__PURE__ */ (0, K.jsxs)("small", { children: ["사용 섹션: ", e.usedInSections.join(", ")] }),
									(e.axisKey || e.researchQuestionId || e.researchRound !== null) && /* @__PURE__ */ (0, K.jsxs)("small", { children: ["추적: ", [
										e.axisKey,
										e.researchQuestionId,
										e.researchRound === null ? "" : `round ${e.researchRound}`
									].filter(Boolean).join(" · ")] }),
									e.url && /* @__PURE__ */ (0, K.jsx)("a", {
										href: e.url,
										target: "_blank",
										rel: "noopener noreferrer",
										children: "원문 열기"
									})
								] }, e.sourceId))
							}) : /* @__PURE__ */ (0, K.jsx)(ws, { children: "확인 가능한 외부 근거 원장이 없습니다." })
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel",
						"data-qa": "dr-data-gaps",
						"aria-labelledby": "dr-data-gaps-heading",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "dr-data-gaps-heading",
							children: "자료 공백"
						}), e.dataGaps.length ? /* @__PURE__ */ (0, K.jsx)("ul", {
							className: "topicrpt-provenance-list",
							children: e.dataGaps.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", {
								"data-severity": e.severity,
								children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.description }), /* @__PURE__ */ (0, K.jsx)("span", { children: e.resolved ? "해결됨" : e.suggestedAction || "추가 확인 필요" })]
							}, e.id))
						}) : /* @__PURE__ */ (0, K.jsx)(ws, { children: "기록된 자료 공백이 없습니다." })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel",
						"data-qa": "dr-quality",
						"aria-labelledby": "dr-quality-heading",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "dr-quality-heading",
							children: "품질과 경고"
						}), e.quality ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsxs)("dl", {
								className: "topicrpt-provenance-facts",
								children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "평가" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [
									e.quality.score ?? "—",
									"점 · ",
									e.quality.grade || "등급 미상"
								] })] }), /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "상태" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e.quality.status || "미기록" })] })]
							}),
							/* @__PURE__ */ (0, K.jsx)("h4", { children: "경고" }),
							Ys(e.quality.warnings, "경고 없음"),
							/* @__PURE__ */ (0, K.jsx)("h4", { children: "보완 제안" }),
							Ys(e.quality.suggestedFixes, "제안 없음")
						] }) : /* @__PURE__ */ (0, K.jsx)(ws, {})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "topicrpt-provenance-panel topicrpt-provenance-wide",
						"data-qa": "dr-collection-resolution",
						"aria-labelledby": "dr-collection-resolution-heading",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "dr-collection-resolution-heading",
							children: "자료 모음 실행 기록"
						}), r ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsxs)("dl", {
								className: "topicrpt-provenance-facts topicrpt-provenance-facts-wide",
								children: [
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "자료 모음" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.collectionId || "직접 범위" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "버전" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.collectionRevision ?? "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "후보" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [r.eligibleTotal ?? "—", "건"] })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "선택 근거" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [r.selectedEvidenceIds.length, "건"] })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "후보 상한" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.candidateCap ?? "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "해결 / 실행" }), /* @__PURE__ */ (0, K.jsxs)("dd", { children: [
										r.resolvedCandidateIds.length,
										" / ",
										r.executionUniverseIds.length,
										"건"
									] })] })
								]
							}),
							/* @__PURE__ */ (0, K.jsxs)("details", { children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "재현성 세부 정보" }), /* @__PURE__ */ (0, K.jsxs)("dl", {
								className: "topicrpt-provenance-facts topicrpt-provenance-facts-wide",
								children: [
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "Definition hash" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.collectionDefinitionHash || "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "Input watermark" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.inputWatermark || "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "Index generation" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.providerGenerations.indexGeneration || "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "RSS generation" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.providerGenerations.rssGeneration || "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "Fingerprint" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.resolutionFingerprint || "—" })] }),
									/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "Resolved at" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: r.resolvedAt || "—" })] })
								]
							})] }),
							r.unusableCandidates.length > 0 && /* @__PURE__ */ (0, K.jsxs)("p", {
								className: "topicrpt-layer-note",
								children: [
									"사용 제외 ",
									r.unusableCandidates.length,
									"건 · ",
									r.unusableCandidates.map((e) => e.reason).join(", ")
								]
							}),
							r.zeroEvidenceRequired && /* @__PURE__ */ (0, K.jsxs)("p", {
								className: "topicrpt-contract-warning",
								children: ["근거 부족 확인: ", r.zeroEvidenceReason || "사유 미기록"]
							})
						] }) : /* @__PURE__ */ (0, K.jsx)(ws, {})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("aside", {
						className: "topicrpt-hypothesis-panel",
						"data-qa": "dr-user-context-hypothesis",
						"aria-labelledby": "dr-user-context-heading",
						children: [
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "section-kicker",
								children: "내 생각·가설 · 근거 아님"
							}),
							/* @__PURE__ */ (0, K.jsx)("h3", {
								id: "dr-user-context-heading",
								children: "사용자 컨텍스트"
							}),
							/* @__PURE__ */ (0, K.jsx)("p", { children: a || "이 보고서에는 사용자 컨텍스트가 기록되지 않았습니다." })
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("aside", {
						className: "topicrpt-hypothesis-panel topicrpt-provenance-wide",
						"data-qa": "dr-overlay-hypothesis",
						"aria-labelledby": "dr-overlay-heading",
						children: [
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "section-kicker",
								children: "내 투자 관점과 비교 · 가설"
							}),
							/* @__PURE__ */ (0, K.jsx)("h3", {
								id: "dr-overlay-heading",
								children: "개인 해석"
							}),
							/* @__PURE__ */ (0, K.jsx)(In, {
								overlay: i,
								staleQa: "dr-overlay-stale"
							})
						]
					})
				]
			})
		]
	});
}
function Es({ resolution: e }) {
	if (!e) return null;
	let t = ls(e), n = typeof e.reason == "string" ? e.reason : "", r = e.injected === !0, i = t?.status || (n === "policy_excluded" ? "excluded" : "unknown"), a = i === "current" && r ? "생성 시점의 현재 상태를 별도 시장 배경으로 포함했습니다." : i === "stale" ? "최신성이 만료되어 보고서 판단에는 주입하지 않았습니다." : i === "fallback" ? "참고용 대체 상태이며 현재 투자 자세로 사용하지 않았습니다." : i === "empty" ? "사용 가능한 시장 상태가 없어 보고서 판단에 포함하지 않았습니다." : i === "excluded" ? "요청 정책에 따라 시장 상태를 제외했습니다." : "시장 상태 참조를 확인할 수 없습니다.";
	return /* @__PURE__ */ (0, K.jsxs)("aside", {
		className: `topicrpt-market-state-context state-${i}`,
		"data-qa": "dr-market-state-context",
		"data-status": i,
		"aria-label": "별도 시장 상태 배경",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장 상태 · 근거 기반 배경" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: i })] }),
			/* @__PURE__ */ (0, K.jsx)("p", { children: a }),
			t ? /* @__PURE__ */ (0, K.jsxs)("dl", { children: [
				/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "기준 시각" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.asOf || "없음" })] }),
				/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "최신성" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.freshnessReason })] }),
				/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "출처" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.sourceKind })] }),
				/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "범위" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t.scope })] })
			] }) : null,
			/* @__PURE__ */ (0, K.jsx)("small", { children: "이 컨텍스트는 외부 근거 목록·인용·가설에 포함되지 않습니다." })
		]
	});
}
var Ds = "custom", Os = { custom: "직접 질문" }, ks = [
	"queued",
	"running",
	"cancel_requested",
	"committing",
	"done",
	"cancelled",
	"failed",
	"failed_cancel",
	"failed_commit",
	"failed_restart",
	"failed_commit_recovery"
];
function As(e, t) {
	return new Promise((n, r) => {
		if (t.aborted) {
			r(new DOMException("Request cancelled", "AbortError"));
			return;
		}
		let i = window.setTimeout(() => {
			t.removeEventListener("abort", a), n();
		}, e), a = () => {
			window.clearTimeout(i), t.removeEventListener("abort", a), r(new DOMException("Request cancelled", "AbortError"));
		};
		t.addEventListener("abort", a, { once: !0 });
	});
}
function js(e) {
	return typeof e == "object" && !!e && !Array.isArray(e);
}
function Ms(e) {
	return typeof e == "string" && ks.includes(e);
}
function Ns(e) {
	return js(e) ? typeof e.id == "string" && Ms(e.status) : !1;
}
function Ps(e) {
	return js(e) ? Ns(e.job) : !1;
}
var Fs = class extends Error {
	job;
	name = "JobTerminalError";
	constructor(e) {
		super(e.message || e.error || `딥 리서치 작업이 ${e.status} 상태로 종료되었습니다.`), this.job = e;
	}
};
async function Is(e, t) {
	let n = e, r = Date.now() + 12e4;
	for (; I(n.status);) {
		if (Date.now() >= r) throw Error("작업이 아직 실행 중입니다. 잠시 후 작업 목록에서 다시 확인하세요.");
		await As(1e3, t), n = await B(`/api/jobs/${encodeURIComponent(n.id)}`, { signal: t });
	}
	if (n.status !== "done") throw new Fs(n);
	return n;
}
function Ls(e = "", t = "딥 리서치") {
	let n = e.replace(/\r\n/g, "\n").split("\n"), r = n.findIndex((e) => e.trim());
	if (r < 0) return {
		title: t,
		body: ""
	};
	let i = n[r].trim().match(/^#\s+(.+)$/);
	return i ? {
		title: i[1],
		body: n.slice(r + 1).join("\n").trim()
	} : {
		title: t,
		body: e
	};
}
function Rs(e) {
	return e.topicLabel || e.topicKey || "딥 리서치";
}
function zs(e) {
	let t = String(e.topicKey || "").trim();
	return Os[t] ? Os[t] : String(e.topicLabel || "").trim() || (t ? t.replace(/_/g, " ") : "기타");
}
function Bs(e) {
	return mn(e) || "날짜 미상";
}
function Vs(e) {
	if (!e) return "월 미상";
	let t = new Date(e);
	if (!Number.isNaN(t.getTime())) return `${t.getFullYear()}.${String(t.getMonth() + 1).padStart(2, "0")}`;
	let n = String(e).match(/^(\d{4})[-.](\d{1,2})/);
	return n ? `${n[1]}.${String(n[2]).padStart(2, "0")}` : "월 미상";
}
function Hs(e) {
	return String(e || "").trim().toLowerCase();
}
var Us = 8;
function Ws(e) {
	window.location.hash = e ? $n(e) : "#/deep-research";
}
function Gs() {
	return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "deep-research";
}
function Ks(e) {
	return e instanceof F ? e.code : e instanceof Fs ? e.job.errorCode || e.job.status : e instanceof Error ? e.name : "request_failed";
}
function qs(e, t) {
	let n = Ks(t);
	return e === "validation" ? "투자 질문을 1~500자로 입력하세요." : n === "evidence_confirmation_required" || n === "resolution_changed" ? "자료 상태가 계획 미리보기와 달라졌습니다. 최신 계획을 다시 미리보고 확인하세요." : n === "no_index" || n === "index_unavailable" ? "연구 인덱스를 아직 읽을 수 없습니다. RSS 자료를 수집하고 인덱스를 만든 뒤 다시 시도하세요." : n === "rss_unavailable" ? "RSS 자료를 읽을 수 없습니다. RSS 수집 상태를 확인한 뒤 다시 시도하세요." : n === "cli_unavailable" ? "선택한 CLI 어댑터를 사용할 수 없습니다. 자동 어댑터를 선택하거나 설정을 확인하세요." : n === "approval_superseded" || n === "approval_expired" || n === "approval_mismatch" ? "이 계획의 승인이 더 이상 유효하지 않습니다. 계획을 다시 미리보고 진행하세요." : e === "degraded" ? "근거가 없는 규칙 기반 보고서를 실행하려면 근거 부족 확인이 필요합니다." : e === "generation" ? "생성 작업에 실패했습니다. 입력과 승인 계획은 유지되므로 다시 실행할 수 있습니다." : e === "report" ? "저장된 리서치를 열지 못했습니다. 목록으로 돌아가 다시 시도하세요." : t instanceof Error && t.message ? t.message : "요청을 처리하지 못했습니다. 입력을 확인하고 다시 시도하세요.";
}
function Js(e) {
	return {
		id: e.approval.id,
		token: e.approval.token
	};
}
function Ys(e, t = "없음") {
	return e.length ? /* @__PURE__ */ (0, K.jsx)("ul", {
		className: "topicrpt-inline-list",
		children: e.map((e) => /* @__PURE__ */ (0, K.jsx)("li", { children: e }, e))
	}) : /* @__PURE__ */ (0, K.jsx)("span", {
		className: "topicrpt-empty-value",
		children: t
	});
}
var Xs = [
	"축 하나를 빼고 공급 쪽을 자세히 봐줘",
	"검색어에 영어 키워드를 더해줘",
	"한국 기업 중심으로 좁혀줘"
];
function Zs({ busy: e, onSubmit: t, onCancel: n }) {
	let [r, i] = (0, l.useState)(""), a = r.trim().length > 0;
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "topicrpt-plan-revision",
		"data-qa": "dr-plan-revision",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("p", {
				className: "topicrpt-plan-revision-head",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "어떻게 고칠까요?" }), /* @__PURE__ */ (0, K.jsx)("span", { children: "요청한 부분만 바꾸고 나머지는 그대로 둡니다. 고친 계획으로 승인이 다시 발급됩니다." })]
			}),
			/* @__PURE__ */ (0, K.jsxs)("label", {
				className: "field",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					className: "sr-only",
					children: "수정 요청"
				}), /* @__PURE__ */ (0, K.jsx)("textarea", {
					rows: 3,
					value: r,
					maxLength: 1e3,
					disabled: e,
					placeholder: "예: 밸류에이션 축은 빼고 공급 쪽을 자세히 봐줘",
					onChange: (e) => i(e.currentTarget.value)
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "topicrpt-plan-revision-examples",
				children: Xs.map((t) => /* @__PURE__ */ (0, K.jsx)("button", {
					className: "chip",
					type: "button",
					disabled: e,
					onClick: () => i(t),
					children: t
				}, t))
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-plan-revision-actions",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn btn--text",
					type: "button",
					onClick: n,
					disabled: e,
					children: "취소"
				}), /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn btn--primary",
					type: "button",
					"data-qa": "dr-plan-revision-submit",
					disabled: e || !a,
					onClick: () => t(r.trim()),
					children: e ? "고치는 중" : "이대로 고치기"
				})]
			})
		]
	});
}
function Qs({ envelope: e, onContinue: t, onEdit: n, degradedConfirming: r, onConfirmDegraded: i, onCancelDegraded: a, editing: o, revising: s, replanning: c, onReplan: l, onEditPlan: u, onRevise: d, onCancelEdit: f }) {
	let { approvedRequest: p, preview: m } = e, h = p.topicPlan, g = m.zeroEvidence, _ = g.reasonCode;
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "input-panel topicrpt-plan-panel",
		"data-qa": "dr-plan",
		"aria-labelledby": "dr-plan-heading",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "input-panel-header",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "section-kicker",
						children: "조사 계획 확인"
					}),
					/* @__PURE__ */ (0, K.jsx)("h2", {
						id: "dr-plan-heading",
						children: "실행 전에 리서치 계획을 확인하세요"
					}),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "계획의 범위와 자료 상태를 확인한 뒤에만 생성 작업을 시작합니다. 이 계획은 승인한 요청의 일부로 기록됩니다." }),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						className: "topicrpt-plan-origin",
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "chip",
							children: Tr(h.plannerMode)
						}), !o && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							"data-qa": "dr-plan-edit",
							onClick: u,
							disabled: c || s,
							children: "계획 고치기"
						}), /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							"data-qa": "dr-plan-replan",
							onClick: l,
							disabled: c || s,
							children: c ? "다시 쓰는 중" : "처음부터 다시"
						})] })]
					})
				]
			}),
			o && /* @__PURE__ */ (0, K.jsx)(Zs, {
				busy: s,
				onSubmit: d,
				onCancel: f
			}),
			!o && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-plan-grid",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-plan-card",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "보고서 유형"
							}),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: wr(h.reportType) }),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "분석 축"
							}),
							h.analysisAxes.length ? /* @__PURE__ */ (0, K.jsx)("ul", {
								className: "topicrpt-axis-list",
								children: h.analysisAxes.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.label }), Ys(e.questions)] }, e.key))
							}) : /* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-empty-value",
								children: "분석 축 없음"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-plan-card",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "검색 질의"
							}),
							Ys(h.searchQueries),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "심층 범위"
							}),
							/* @__PURE__ */ (0, K.jsxs)("p", { children: [
								"최대 ",
								h.deepResearch.maxRounds,
								"라운드 · 하위 질문 ",
								h.deepResearch.subQuestions.length,
								"개"
							] }),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "예상 공백"
							}),
							Ys(h.dataGapsLikely)
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-plan-card",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "저장한 자료 모음"
							}),
							p.collectionRef ? /* @__PURE__ */ (0, K.jsxs)("p", { children: [
								"저장한 자료 모음 사용 · ",
								p.collectionRef.id,
								" · 버전 ",
								p.collectionRef.revision,
								/* @__PURE__ */ (0, K.jsx)("br", {}),
								"후보 ",
								m.resolution.eligibleTotal ?? 0,
								"건 · 선택 ",
								m.resolution.selectedEvidenceIds.length,
								"건",
								/* @__PURE__ */ (0, K.jsx)("br", {}),
								/* @__PURE__ */ (0, K.jsx)("small", { children: "자료 모음은 근거 자체가 아니며, 일치하는 자료를 실행 시점에 다시 확인합니다." })
							] }) : /* @__PURE__ */ (0, K.jsx)("p", { children: "저장한 자료 모음 없이 전체 허용 자료에서 확인합니다." }),
							g.required && /* @__PURE__ */ (0, K.jsxs)("p", {
								className: "topicrpt-zero-evidence",
								"data-qa": `dr-readiness-${_ === "no_index" ? "no-index" : _ || "zero-evidence"}`,
								"data-reason-code": _ || void 0,
								children: [_ === "no_index" ? "인덱스 없음" : _ === "filtered_empty" ? "필터 결과 없음" : "일치 자료 없음", " · 실행 전 확인 필요"]
							}),
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-plan-label",
								children: "시장 상태 배경"
							}),
							/* @__PURE__ */ (0, K.jsxs)("p", { children: [
								p.marketStatePolicy === "exclude" ? "제외" : "현재 상태 포함",
								" · 범위 ",
								p.marketStateScope === "AUTO" ? "자동" : p.marketStateScope,
								/* @__PURE__ */ (0, K.jsx)("br", {}),
								/* @__PURE__ */ (0, K.jsx)("small", { children: "실행 시 상태, 기준 시각, 최신성, 출처를 별도 배경으로 기록합니다." })
							] })
						]
					})
				]
			}),
			g.required && _ && g.resolutionFingerprint && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-degraded-panel",
				"data-qa": `dr-degraded-${_ === "no_index" ? "no-index" : _}`,
				"data-reason-code": _,
				role: "alert",
				children: [
					/* @__PURE__ */ (0, K.jsx)("strong", { children: "근거 부족 상태를 확인해야 합니다" }),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "현재 선택된 외부 근거가 0건입니다. 확인하면 규칙 기반 결과로 진행하며, 보고서에 근거 공백과 반대 근거를 표시합니다." }),
					r ? /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-degraded-actions",
						children: [/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							"data-qa": "dr-degraded-confirm",
							onClick: i,
							children: "근거 부족을 확인하고 계속"
						}), /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							onClick: a,
							children: "취소"
						})]
					}) : /* @__PURE__ */ (0, K.jsx)("p", { children: "계속하기를 누르면 확인 단계가 열립니다." })
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "topicrpt-action-row",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: n,
					children: "질문 수정"
				}), /* @__PURE__ */ (0, K.jsx)("button", {
					className: r ? "btn" : "btn btn--primary",
					type: "button",
					"data-qa": "dr-continue",
					onClick: t,
					children: g.required ? "계속하기" : "이 계획으로 생성"
				})]
			})
		]
	});
}
function $s() {
	let e = fn("topicReport"), [t, n] = (0, l.useState)([]), [r, i] = (0, l.useState)(null), a = (0, l.useMemo)(() => er(window.location.hash), []), [o, s] = (0, l.useState)(a.kind === "report" ? a.id : ""), [c, u] = (0, l.useState)(a.kind === "collection" ? a.id : ""), [d, f] = (0, l.useState)(a.malformed), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(""), [v, y] = (0, l.useState)("include_current"), [b, x] = (0, l.useState)("AUTO"), [S, C] = (0, l.useState)(null), [w, T] = (0, l.useState)(!1), [E, D] = (0, l.useState)("readiness"), [O, k] = (0, l.useState)(null), [A, j] = (0, l.useState)(!1), [M, N] = (0, l.useState)(!1), [P, I] = (0, l.useState)(""), [L, R] = (0, l.useState)(null), [z, H] = (0, l.useState)(""), [U, ee] = (0, l.useState)(null), [te, W] = (0, l.useState)(""), [G, q] = (0, l.useState)(""), [ne, re] = (0, l.useState)(0), [ie, ae] = (0, l.useState)("auto"), [oe, ce] = (0, l.useState)(!1), [le, ue] = (0, l.useState)(!1), [de, fe] = (0, l.useState)(!1), [pe, me] = (0, l.useState)(""), [he, ge] = (0, l.useState)("recent"), _e = (0, l.useRef)(0), ve = (0, l.useRef)(null), ye = (0, l.useRef)(null), be = (0, l.useRef)(""), xe = (0, l.useRef)(!1), Se = Ds, Ce = m, we = (0, l.useCallback)(() => {
		ve.current?.abort();
		let e = new AbortController();
		return ve.current = e, _e.current += 1, {
			id: _e.current,
			signal: e.signal
		};
	}, []), Te = (0, l.useCallback)((e) => e === _e.current, []), Ee = (0, l.useCallback)(async (e) => {
		N(!0);
		try {
			let t = await B("/api/topic-reports", { signal: e });
			n(Sr(t)), ee(null), D((e) => e === "readiness" ? "draft" : e), Qe("deep-research", {
				surface: "topic_report",
				viewId: "topicrpt",
				reportKind: "",
				reportId: "",
				collectionId: null,
				collectionRevision: null
			});
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") return;
			I(qs("readiness", e)), R("readiness"), H(Ks(e));
			let t = Ks(e);
			ee(t === "no_index" || t === "index_unavailable" ? "no-index" : t === "rss_unavailable" ? "rss" : "api"), D("recoverable-error");
		} finally {
			N(!1);
		}
	}, []);
	(0, l.useEffect)(() => {
		let e = new AbortController();
		return Ee(e.signal), () => e.abort();
	}, [Ee, e]), (0, l.useEffect)(() => {
		let e = {
			collectionId: S?.id || null,
			collectionRevision: S?.revision || null
		};
		return $e("deep-research", e), () => {
			let t = window.FolioAgent?.currentContext;
			t?.collectionId === e.collectionId && t.collectionRevision === e.collectionRevision && $e("deep-research", {
				collectionId: null,
				collectionRevision: null
			});
		};
	}, [S]), (0, l.useEffect)(() => {
		let e = () => {
			if (!Gs()) return;
			let e = er(window.location.hash);
			f(e.malformed), s(e.kind === "report" ? e.id : ""), u(e.kind === "collection" ? e.id : ""), e.malformed && (i(null), I(e.kind === "collection" ? "컬렉션 주소 형식이 올바르지 않습니다. 목록으로 돌아가 다시 여세요." : "보고서 주소 형식이 올바르지 않습니다. 목록으로 돌아가 다시 여세요."), R("report"), H(e.kind === "collection" ? "malformed_collection_id" : "malformed_report_id"), D("recoverable-error"));
		};
		return window.addEventListener("hashchange", e), e(), () => window.removeEventListener("hashchange", e);
	}, []);
	let De = (0, l.useCallback)(() => {
		xe.current = !0, i(null), f(!1), I(""), R(null), H(""), Ws();
	}, []);
	(0, l.useEffect)(() => {
		o || d || !xe.current || (xe.current = !1, window.requestAnimationFrame(() => {
			let e = be.current.replace(/["\\]/g, "");
			((e ? document.querySelector("[data-report-id=\"" + e + "\"]") : null) || ye.current)?.focus({ preventScroll: !0 });
		}));
	}, [
		o,
		d,
		E
	]), (0, l.useEffect)(() => {
		let e = (e) => {
			let t = e.detail;
			Re(t, window.FolioAgent?.currentContext) && re((e) => e + 1);
		};
		return window.addEventListener(se, e), () => window.removeEventListener(se, e);
	}, []), (0, l.useEffect)(() => {
		let e = new AbortController();
		ve.current?.abort();
		let t = _e.current + 1;
		_e.current = t;
		async function n(n) {
			N(!0), I(""), R(null), H("");
			try {
				let r = await B(`/api/topic-reports/${encodeURIComponent(n)}?includePersonal=true`, { signal: e.signal });
				if (e.signal.aborted || _e.current !== t) return;
				let a = xr(r);
				i(a), D("report"), Qe("deep-research", {
					surface: "topic_report_reader",
					viewId: "topicrpt",
					reportKind: "topic_report",
					reportId: a.id || n,
					collectionId: S?.id || null,
					collectionRevision: S?.revision || null
				});
			} catch (n) {
				if (n instanceof DOMException && n.name === "AbortError" || e.signal.aborted || _e.current !== t) return;
				i(null), I(qs("report", n)), R("report"), H(Ks(n)), D("recoverable-error");
			} finally {
				!e.signal.aborted && _e.current === t && N(!1);
			}
		}
		return o && !d ? n(o) : !d && !c && (i(null), D((e) => e === "report" ? "draft" : e), Qe("deep-research", {
			surface: "topic_report",
			viewId: "topicrpt",
			reportKind: "",
			reportId: "",
			collectionId: S?.id || null,
			collectionRevision: S?.revision || null
		}), N(!1)), () => e.abort();
	}, [
		c,
		o,
		d,
		ne
	]);
	let Oe = async (e) => {
		e.preventDefault();
		let t = m.normalize("NFKC").trim();
		if (!t || t.length > 500) {
			I(qs("validation", /* @__PURE__ */ Error("question_invalid"))), R("validation"), H("question_invalid"), D("recoverable-error");
			return;
		}
		let n = we();
		D("plan-loading"), k(null), j(!1), I(""), R(null), H(""), W(ie === "rules" ? "질문을 실행 계획으로 바꾸는 중입니다." : "AI가 리서치 계획을 쓰는 중입니다. 30초 이상 걸릴 수 있습니다.");
		let r = {
			question: t,
			userContext: g.normalize("NFKC").trim(),
			plannerEngine: ie,
			deepResearch: !0,
			customTickers: {},
			marketStatePolicy: v,
			marketStateScope: b,
			collectionRef: S
		};
		try {
			let e = await V("/api/topic-reports/plan", r, { signal: n.signal });
			if (!Te(n.id)) return;
			k(e), D("plan-review"), W("실행 계획을 확인하세요.");
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || !Te(n.id)) return;
			I(qs("plan", e)), R("plan"), H(Ks(e)), ee(Ks(e) === "no_index" || Ks(e) === "index_unavailable" ? "no-index" : Ks(e) === "rss_unavailable" ? "rss" : null), D("recoverable-error"), W("");
		}
	}, ke = async (e) => {
		let t = we();
		D("generation"), I(""), R(null), H(""), W("승인된 계획으로 리서치를 생성하는 중입니다.");
		let r = {
			mode: "auto",
			adapter: "auto",
			fallbackPolicy: p
		}, a = {
			approvedRequest: e.approvedRequest,
			approval: Js(e),
			execution: r
		};
		try {
			let e = await V("/api/topic-reports", a, { signal: t.signal }), r = Ps(e) ? e.job : Ns(e) ? e : null;
			if (!r) throw Error("생성 작업 ID를 확인하지 못했습니다.");
			let o = await Is(r, t.signal);
			if (!Te(t.id)) return;
			let s = o.result?.reportId || o.result?.artifactId || "";
			if (!s) throw Error("생성된 보고서 ID를 확인하지 못했습니다.");
			let c = xr(await B(`/api/topic-reports/${encodeURIComponent(s)}?includePersonal=true`, { signal: t.signal }));
			if (!Te(t.id)) return;
			n((e) => [c, ...e.filter((e) => e.id !== c.id)]), i(c), D("report"), W("딥 리서치를 생성하고 자동 저장했습니다."), Ws(c.id), Qe("deep-research", {
				surface: "topic_report_reader",
				viewId: "topicrpt",
				reportKind: "topic_report",
				reportId: c.id || "",
				collectionId: S?.id || null,
				collectionRevision: S?.revision || null
			});
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || !Te(t.id)) return;
			I(qs("generation", e)), R(e instanceof F && (e.code === "evidence_confirmation_required" || e.code === "resolution_changed") ? "degraded" : "generation"), H(Ks(e)), D("recoverable-error"), W("");
		}
	}, Ae = () => {
		if (O) {
			if (O.preview.zeroEvidence.required) {
				if (!O.preview.zeroEvidence.reasonCode || !O.preview.zeroEvidence.resolutionFingerprint) {
					I("근거 부족 확인 정보가 없어 실행을 중단했습니다. 계획을 다시 미리보세요."), R("degraded"), H("invalid_zero_evidence"), D("recoverable-error");
					return;
				}
				j(!0), W("근거 부족 확인을 검토하세요.");
				return;
			}
			ke(O);
		}
	}, je = async (e) => {
		if (!O) return;
		let t = we(), n = e.length > 0;
		n ? ue(!0) : fe(!0), I(""), R(null), H(""), W(n ? "요청하신 대로 계획을 고치는 중입니다. 30초 이상 걸릴 수 있습니다." : "AI가 리서치 계획을 다시 쓰는 중입니다. 30초 이상 걸릴 수 있습니다.");
		let r = {
			approvedRequest: O.approvedRequest,
			approval: Js(O),
			instruction: e
		};
		try {
			let e = await V("/api/topic-reports/plan/replan", r, { signal: t.signal });
			if (!Te(t.id)) return;
			k(e), ce(!1), j(!1), W(e.approvedRequest.topicPlan.plannerMode === "llm" ? n ? "요청하신 대로 계획을 고쳤습니다." : "AI가 계획을 다시 썼습니다." : "AI 엔진을 쓸 수 없어 계획을 그대로 두었습니다.");
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || !Te(t.id)) return;
			I(qs("plan", e)), R("plan"), H(Ks(e)), D("recoverable-error"), W("");
		} finally {
			Te(t.id) && (fe(!1), ue(!1));
		}
	}, Me = async (e) => {
		await je(e);
	}, Ne = async () => {
		if (!O) return;
		let e = O.preview.zeroEvidence;
		if (!e.required || !e.reasonCode || !e.resolutionFingerprint) return;
		let t = we();
		I(""), R(null), H(""), W("근거 부족 확인을 저장하는 중입니다.");
		let n = {
			approvedRequest: O.approvedRequest,
			approval: Js(O),
			reasonCode: e.reasonCode,
			resolutionFingerprint: e.resolutionFingerprint,
			confirmed: !0
		};
		try {
			let e = await V("/api/topic-reports/confirm-degraded", n, { signal: t.signal });
			if (!Te(t.id)) return;
			k(e), j(!1), await ke(e);
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError" || !Te(t.id)) return;
			I(qs("degraded", e)), R("degraded"), H(Ks(e)), D("recoverable-error"), W("");
		}
	};
	async function Pe(e) {
		if (!(!e.id || !window.confirm(`${Rs(e)} 보고서를 삭제할까요?`))) {
			q(`delete-${e.id}`), I("");
			try {
				let t = await fetch(`/api/topic-reports/${encodeURIComponent(e.id)}`, { method: "DELETE" });
				if (!t.ok) throw Error(`삭제 실패: ${t.status}`);
				r?.id === e.id && Ws(), n((t) => t.filter((t) => t.id !== e.id)), W("저장된 딥 리서치를 삭제했습니다.");
			} catch (e) {
				I(e instanceof Error ? e.message : "보고서 삭제에 실패했습니다."), R("report"), H(Ks(e));
			} finally {
				q("");
			}
		}
	}
	async function Fe(e) {
		if (r) {
			q(e), W(e === "notion" ? "Notion으로 내보내는 중..." : "Obsidian으로 내보내는 중...");
			try {
				let t = e === "notion" ? await V("/api/export-notion/topic-report", r) : await V("/api/export-obsidian/topic-report", r);
				W(e === "notion" ? `Notion으로 내보냈습니다${t.title ? `: ${t.title}` : ""}` : `Obsidian으로 내보냈습니다${t.topic || t.filename ? `: ${t.topic || t.filename}` : ""}`);
			} catch (e) {
				W(e instanceof Error ? e.message : "내보내기에 실패했습니다.");
			} finally {
				q("");
			}
		}
	}
	async function Ie() {
		if (r?.id) {
			q("overlay"), W("내 노트와 연결하는 중...");
			try {
				let e = await V(`/api/topic-reports/${encodeURIComponent(r.id)}/personal-overlay`, {});
				Ns(e) && await Is(e, new AbortController().signal);
				let t = xr(await B(`/api/topic-reports/${encodeURIComponent(r.id)}?includePersonal=true`));
				i(t), W("내 노트와 연결했습니다.");
			} catch (e) {
				W(e instanceof Error ? e.message : "내 노트 연결에 실패했습니다.");
			} finally {
				q("");
			}
		}
	}
	let Le = (0, l.useMemo)(() => {
		let e = Hs(pe);
		return e ? t.filter((t) => Hs([
			Rs(t),
			zs(t),
			t.topicKey,
			t.engine,
			t.engineDetail,
			Bs(t.generatedAt || t.date)
		].filter(Boolean).join(" ")).includes(e)) : t;
	}, [pe, t]), ze = (0, l.useMemo)(() => {
		let e = (e) => String(e.generatedAt || e.date || ""), t = [...Le].sort((t, n) => e(n).localeCompare(e(t)));
		if (he === "recent") return t.length ? [{
			key: `최근 리서치 ${Math.min(t.length, Us)}건`,
			rows: t.slice(0, Us)
		}] : [];
		let n = /* @__PURE__ */ new Map();
		for (let e of t) {
			let t = he === "month" ? Vs(e.generatedAt || e.date) : zs(e);
			n.has(t) || n.set(t, []), n.get(t)?.push(e);
		}
		return Array.from(n.entries()).map(([e, t]) => ({
			key: e,
			rows: t
		})).sort((t, n) => e(n.rows[0]).localeCompare(e(t.rows[0])));
	}, [Le, he]), Be = Ls(r?.markdown || "", r ? Rs(r) : "딥 리서치"), Ve = us(r?.marketStateResolution), He = (0, l.useCallback)((e) => {
		let t = e.source === "both" ? "포트폴리오·워치리스트" : e.source === "portfolio" ? "포트폴리오" : "워치리스트", n = `개인 맥락(hypothesis): ${e.ticker} · ${t}`;
		_((e) => {
			let t = e.split("\n").map((e) => e.trim()).filter(Boolean);
			return t.includes(n) ? e : [...t, n].join("\n").slice(0, 4e3);
		});
	}, []);
	if (c && !d) return /* @__PURE__ */ (0, K.jsx)("div", {
		className: "react-deep-research-route",
		"data-deep-research-route": !0,
		children: /* @__PURE__ */ (0, K.jsx)(Ss, {
			collectionId: c,
			onBack: () => Ws(),
			onStartResearch: (e) => {
				C(e), Ws();
			}
		})
	});
	if (o && !r && (E !== "recoverable-error" || L !== "report")) return /* @__PURE__ */ (0, K.jsx)("div", {
		className: "react-deep-research-route",
		"data-deep-research-route": !0,
		children: /* @__PURE__ */ (0, K.jsxs)("section", {
			className: "topicrpt-report-state",
			"data-qa": "dr-report-loading",
			role: "status",
			"aria-live": "polite",
			"aria-busy": "true",
			children: [
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "section-kicker",
					children: "DEEP RESEARCH"
				}),
				/* @__PURE__ */ (0, K.jsx)("h1", {
					tabIndex: -1,
					children: "저장된 리서치를 여는 중입니다"
				}),
				/* @__PURE__ */ (0, K.jsx)("p", { children: "보고서 본문과 함께 사용한 자료 목록을 불러오는 중입니다." })
			]
		})
	});
	if ((o || d) && !r && (d || E === "recoverable-error" && L === "report")) {
		let e = z === "topic_report_not_found" || z === "not_found";
		return /* @__PURE__ */ (0, K.jsx)("div", {
			className: "react-deep-research-route",
			"data-deep-research-route": !0,
			children: /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "topicrpt-report-state is-error",
				"data-qa": e ? "dr-report-not-found" : "dr-report-error",
				role: "alert",
				"aria-live": "assertive",
				children: [
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "DEEP RESEARCH"
					}),
					/* @__PURE__ */ (0, K.jsx)("h1", { children: e ? "저장된 리서치를 찾을 수 없습니다" : "리서치를 열 수 없습니다" }),
					/* @__PURE__ */ (0, K.jsx)("p", {
						"data-qa": e ? "dr-not-found" : void 0,
						children: P || "보고서 주소나 저장 데이터를 확인한 뒤 목록에서 다시 여세요."
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						"data-qa": "dr-report-return",
						onClick: De,
						children: "딥 리서치 목록으로 돌아가기"
					})
				]
			})
		});
	}
	if (r && E === "report") return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-deep-research-route",
		"data-deep-research-route": !0,
		"data-qa": "dr-report",
		children: [
			P && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				"data-qa": "dr-error-report",
				children: P
			}),
			(r.mode === "fallback" || r.generation?.mode === "rules") && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				"data-qa": "dr-degraded-rules",
				role: "status",
				children: "근거 부족을 확인한 규칙 기반 보고서입니다. 자료 공백과 반대 근거를 함께 확인하세요."
			}),
			/* @__PURE__ */ (0, K.jsxs)(Yn, {
				eyebrow: `DEEP RESEARCH${r.date ? ` · ${r.date}` : ""}`,
				title: Be.title,
				meta: `${Rs(r)} · 뉴스 ${r.docCount || 0}건 · 내러티브 ${r.memoryCount || 0}건`,
				agentContext: {
					surface: "topic_report_reader",
					viewId: "topicrpt",
					reportKind: "topic_report",
					reportId: r.id || "",
					topic: Rs(r),
					marketState: Ve
				},
				breadcrumb: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					"data-qa": "dr-report-return",
					onClick: De,
					children: "딥 리서치"
				}), /* @__PURE__ */ (0, K.jsx)("span", { children: Be.title })] }),
				onClose: De,
				actionSlot: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
					/* @__PURE__ */ (0, K.jsx)(bn, {
						title: "AI",
						children: /* @__PURE__ */ (0, K.jsx)(xn, {
							icon: "agent",
							onClick: () => nt({
								surface: "topic_report_reader",
								reportKind: "topic_report",
								reportId: r.id || "",
								topic: Rs(r),
								message: `${Be.title}의 핵심 결론, 반대 근거, 더 발전시킬 분석 방향을 정리해줘.`,
								autoSubmit: !0
							}),
							children: "Agent에게 묻기"
						})
					}),
					/* @__PURE__ */ (0, K.jsx)(bn, {
						title: "노트",
						children: /* @__PURE__ */ (0, K.jsx)(xn, {
							icon: "link",
							"data-qa": "dr-overlay-generate",
							disabled: G === "overlay" || !r.id,
							onClick: Ie,
							children: G === "overlay" ? "연결 중" : "내 노트와 연결"
						})
					}),
					/* @__PURE__ */ (0, K.jsxs)(bn, {
						title: "내보내기",
						children: [/* @__PURE__ */ (0, K.jsx)(xn, {
							icon: "notion",
							disabled: G === "notion",
							onClick: () => Fe("notion"),
							children: G === "notion" ? "내보내는 중" : "Notion으로 내보내기"
						}), /* @__PURE__ */ (0, K.jsx)(xn, {
							icon: "obsidian",
							disabled: G === "obsidian",
							onClick: () => Fe("obsidian"),
							children: G === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"
						})]
					}),
					r.generation?.message && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "react-reader-status",
						children: r.generation.message
					}),
					te && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "react-reader-status",
						children: te
					})
				] }),
				noteIdentity: {
					id: qn("topic", Rs(r)),
					noteType: "topic_review",
					title: Rs(r) ? `${Rs(r)} 리서치 노트` : "딥 리서치 노트",
					topic: Rs(r),
					label: Rs(r),
					reportKind: "topic_report",
					reportId: Rs(r),
					linkedReports: [Be.title].filter(Boolean)
				},
				noteLinkedTitle: Be.title,
				noteOverlay: yr(r.personalOverlay, r.canonicalRevision),
				children: [
					/* @__PURE__ */ (0, K.jsx)(Es, { resolution: r.marketStateResolution }),
					/* @__PURE__ */ (0, K.jsx)(On, { markdown: Be.body || r.markdown || "" }),
					/* @__PURE__ */ (0, K.jsx)(Ts, { report: r })
				]
			})
		]
	});
	let Ue = E === "plan-loading" || E === "generation" || M || w, We = E === "recoverable-error" && P;
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-deep-research-route",
		"data-deep-research-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Deep Research",
				title: "딥 리서치",
				description: "투자 질문을 실행 계획으로 정리해 확인한 뒤, 정해진 자료 범위 안에서 근거를 구분한 보고서를 생성합니다.",
				actions: /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: () => void Ee(),
					disabled: M,
					children: M ? "불러오는 중" : "새로고침"
				})
			}),
			E === "readiness" && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				"data-qa": "dr-readiness-loading",
				role: "status",
				children: "저장된 리서치와 자료 상태를 확인하는 중입니다."
			}),
			U && E === "recoverable-error" && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				"data-qa": `dr-readiness-${U}`,
				children: P
			}),
			We && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-dashboard-error topicrpt-recoverable-error",
				"data-qa": `dr-error-${L || "request"}`,
				role: "alert",
				children: [
					/* @__PURE__ */ (0, K.jsx)("strong", { children: "다시 시도할 수 있습니다" }),
					/* @__PURE__ */ (0, K.jsx)("span", {
						"data-qa": `dr-error-${(z || "request").replace(/_/g, "-")}`,
						"data-error-code": z || "request",
						children: P
					}),
					/* @__PURE__ */ (0, K.jsx)("p", { children: "입력한 질문과 컨텍스트, 마지막 계획은 유지됩니다." }),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => {
							I(""), R(null), H(""), D(O ? "plan-review" : "draft");
						},
						children: "돌아가서 수정"
					})
				]
			}),
			E !== "plan-review" && E !== "generation" && /* @__PURE__ */ (0, K.jsxs)("form", {
				className: "input-panel topicrpt-form",
				onSubmit: Oe,
				noValidate: !0,
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "input-panel-header",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "section-kicker",
								children: "투자 질문"
							}),
							/* @__PURE__ */ (0, K.jsx)("h2", { children: "무엇을 투자 판단으로 확인하고 싶나요?" }),
							/* @__PURE__ */ (0, K.jsx)("p", { children: "질문은 1~500자로 입력하세요. 추가로 적는 조건은 내 생각(가설)로만 전달되며 외부 근거로 쓰이지 않습니다." })
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field topicrpt-question-field",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", { children: "투자 질문" }),
							/* @__PURE__ */ (0, K.jsx)("textarea", {
								"data-qa": "dr-question",
								value: m,
								onChange: (e) => h(e.currentTarget.value),
								maxLength: 500,
								rows: 4,
								placeholder: "예: 미국 전력 수요 증가가 12개월 내 반도체 공급망과 관련 기업에 어떤 영향을 줄까?",
								required: !0,
								"aria-describedby": "dr-question-help"
							}),
							/* @__PURE__ */ (0, K.jsxs)("small", {
								id: "dr-question-help",
								children: [m.length, "/500"]
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("details", {
						className: "topicrpt-advanced",
						"data-qa": "dr-advanced",
						open: !!(g.trim() || S),
						children: [
							/* @__PURE__ */ (0, K.jsxs)("summary", { children: ["분석 조건 추가 ", /* @__PURE__ */ (0, K.jsx)("em", { children: "(선택)" })] }),
							/* @__PURE__ */ (0, K.jsxs)("label", {
								className: "field topicrpt-context-field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "추가 조건" }), /* @__PURE__ */ (0, K.jsx)("textarea", {
									"data-qa": "dr-context",
									value: g,
									onChange: (e) => _(e.currentTarget.value),
									maxLength: 4e3,
									rows: 4,
									placeholder: "예: 보유 종목, 관심 지역, 확인할 기간 등. 이 내용은 내 생각(가설)로 표시됩니다."
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)(ln, {
								mode: "deep-research",
								onReference: He
							}),
							/* @__PURE__ */ (0, K.jsx)(xs, {
								selectedRef: S,
								onSelectedRef: C,
								onBusyChange: T,
								onOpenDetail: (e) => {
									window.location.hash = Qn(e);
								},
								disabled: E === "plan-loading" || M
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "topicrpt-policy-row",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field topicrpt-policy-field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장 상태 배경" }), /* @__PURE__ */ (0, K.jsxs)("select", {
										value: v,
										onChange: (e) => y(e.currentTarget.value),
										children: [/* @__PURE__ */ (0, K.jsx)("option", {
											value: "include_current",
											children: "현재 상태 포함"
										}), /* @__PURE__ */ (0, K.jsx)("option", {
											value: "exclude",
											children: "제외"
										})]
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field topicrpt-policy-field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장 상태 범위" }), /* @__PURE__ */ (0, K.jsxs)("select", {
										value: b,
										onChange: (e) => x(e.currentTarget.value),
										children: [
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "AUTO",
												children: "자동"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "GLOBAL",
												children: "글로벌"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "US",
												children: "미국"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "KR",
												children: "한국"
											})
										]
									})]
								})]
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "topicrpt-action-row",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "topicrpt-policy-note",
								children: "심층 조사 · 최대 2라운드"
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "topicrpt-planner-choice",
								children: [/* @__PURE__ */ (0, K.jsx)("span", {
									id: "dr-planner-engine-label",
									children: "계획 작성"
								}), /* @__PURE__ */ (0, K.jsx)("div", {
									className: "segment",
									"data-qa": "dr-planner-engine",
									role: "group",
									"aria-labelledby": "dr-planner-engine-label",
									children: Cs.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": ie === e.value,
										disabled: Ue,
										"data-tooltip": e.hint,
										onClick: () => ae(e.value),
										children: e.label
									}, e.value))
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn btn--primary",
								type: "submit",
								"data-qa": "dr-preview",
								disabled: Ue,
								children: E === "plan-loading" ? ie === "rules" ? "계획 준비 중" : "AI가 계획을 쓰는 중" : "계획 미리보기"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsx)("input", {
						type: "hidden",
						value: Ce,
						"data-legacy-topic": Se,
						readOnly: !0,
						"aria-hidden": "true"
					}),
					/* @__PURE__ */ (0, K.jsx)("input", {
						type: "hidden",
						value: "true",
						readOnly: !0,
						"aria-hidden": "true"
					})
				]
			}),
			E === "plan-review" && O && /* @__PURE__ */ (0, K.jsx)(Qs, {
				envelope: O,
				onContinue: Ae,
				onEdit: () => {
					D("draft"), ce(!1), W("");
				},
				editing: oe,
				revising: le,
				replanning: de,
				onReplan: () => void je(""),
				onEditPlan: () => ce(!0),
				onRevise: (e) => void Me(e),
				onCancelEdit: () => ce(!1),
				degradedConfirming: A,
				onConfirmDegraded: () => void Ne(),
				onCancelDegraded: () => j(!1)
			}),
			E === "generation" && /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "input-panel topicrpt-generation-panel",
				"data-qa": "dr-generation",
				"aria-live": "polite",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "section-kicker",
						children: "생성 중"
					}),
					/* @__PURE__ */ (0, K.jsx)("h2", { children: "승인한 계획을 실행하는 중입니다" }),
					/* @__PURE__ */ (0, K.jsx)("p", {
						"data-qa": "dr-generation-status",
						children: te || "작업 상태를 확인하는 중입니다."
					})
				]
			}),
			te && E !== "generation" && E !== "report" && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				"data-qa": "dr-status",
				role: "status",
				children: te
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "find-bar",
				"aria-label": "저장된 리서치 검색",
				children: [
					/* @__PURE__ */ (0, K.jsx)("input", {
						className: "find-bar__search",
						type: "search",
						value: pe,
						onChange: (e) => me(e.currentTarget.value),
						placeholder: "주제·질문·모델 검색",
						"aria-label": "저장된 리서치 검색"
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "find-bar__field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "보기" }), /* @__PURE__ */ (0, K.jsxs)("select", {
							"aria-label": "저장된 리서치 보기 방식",
							value: he,
							onChange: (e) => ge(e.currentTarget.value),
							children: [
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "recent",
									children: "최근"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "topic",
									children: "주제별"
								}),
								/* @__PURE__ */ (0, K.jsx)("option", {
									value: "month",
									children: "월별"
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--text find-bar__reset",
						type: "button",
						onClick: () => {
							me(""), ge("recent");
						},
						children: "초기화"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "react-analysis-feed",
				"aria-label": "저장된 리서치",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-section-heading",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "Saved Research"
					}), /* @__PURE__ */ (0, K.jsx)("h2", {
						ref: ye,
						tabIndex: -1,
						children: "저장된 리서치"
					})] }), /* @__PURE__ */ (0, K.jsx)("span", {
						"aria-live": "polite",
						children: `${Le.length}건${pe ? " · 검색 결과" : ""}`
					})]
				}), ze.length ? ze.map((e) => /* @__PURE__ */ (0, K.jsxs)("section", {
					className: "report-feed-group",
					children: [/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "report-feed-group-head",
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-name",
							children: e.key
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "report-feed-group-meta",
							children: hn(e.rows.length, e.rows[0]?.generatedAt || e.rows[0]?.date)
						})]
					}), /* @__PURE__ */ (0, K.jsx)("div", {
						className: "report-feed-group-cards",
						children: e.rows.map((e) => {
							let t = G === `delete-${e.id}`;
							return /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "report-feed-card-wrap",
								children: [/* @__PURE__ */ (0, K.jsxs)("button", {
									className: "report-feed-card is-topic",
									type: "button",
									"data-report-id": e.id,
									onClick: () => {
										e.id && (be.current = e.id, Ws(e.id));
									},
									children: [
										/* @__PURE__ */ (0, K.jsx)("span", {
											className: "report-feed-card-meta",
											children: (e.engine || e.mode) && /* @__PURE__ */ (0, K.jsxs)("span", {
												className: "report-feed-badge",
												children: [e.engine || String(e.mode).toUpperCase(), gn(e.engine, e.engineDetail) && /* @__PURE__ */ (0, K.jsx)("em", { children: gn(e.engine, e.engineDetail) })]
											})
										}),
										/* @__PURE__ */ (0, K.jsx)("strong", { children: Rs(e) }),
										/* @__PURE__ */ (0, K.jsxs)("span", {
											className: "report-feed-card-foot",
											children: ["생성일 ", Bs(e.date || e.generatedAt)]
										})
									]
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									className: "btn btn--icon report-feed-card-delete",
									disabled: t,
									onClick: () => void Pe(e),
									"aria-label": `${Rs(e)} 삭제`,
									"data-tooltip": "삭제",
									"data-tooltip-pos": "bottom",
									children: /* @__PURE__ */ (0, K.jsx)("svg", {
										width: "13",
										height: "13",
										viewBox: "0 0 16 16",
										fill: "none",
										stroke: "currentColor",
										strokeWidth: "1.4",
										strokeLinecap: "round",
										strokeLinejoin: "round",
										"aria-hidden": "true",
										children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" })
									})
								})]
							}, e.id || `${Rs(e)}-${e.date}`);
						})
					})]
				}, e.key)) : /* @__PURE__ */ (0, K.jsx)("div", {
					className: "report-feed-empty",
					"data-qa": "dr-report-list-empty",
					children: pe ? "검색 결과가 없습니다." : "저장된 딥 리서치가 없습니다. 질문을 입력해 실행 계획을 미리보세요."
				})]
			})
		]
	});
}
//#endregion
//#region src/islands/MarketStateDashboard.tsx
var ec = {
	high: "높음",
	medium: "보통",
	low: "낮음"
}, tc = [
	"overall",
	"us",
	"kr",
	"europe",
	"jp"
], nc = {
	overall: "종합",
	us: "US",
	kr: "KR",
	europe: "EU",
	jp: "JP"
};
function rc(e) {
	let t = [], n = 0;
	for (let r = 0; r < e.length; r += 1) {
		let i = e[r];
		if (i !== "." && i !== "!" && i !== "?" && i !== "。") continue;
		let a = e[r + 1];
		i !== "。" && (a && !/\s/.test(a) || /\d/.test(e[r - 1] || "") && /\d/.test(a || "")) || (t.push(e.slice(n, r + 1).trim()), n = r + 1);
	}
	let r = e.slice(n).trim();
	return r && t.push(r), t.filter(Boolean);
}
function ic(e) {
	let t = String(e || "").replace(/\s+/g, " ").trim(), n = rc(t);
	return {
		lead: n[0] || t,
		support: n.slice(1).join(" ")
	};
}
function ac(e) {
	if (!e) return "";
	let t = new Date(e);
	return Number.isNaN(t.getTime()) ? e : t.toLocaleString("ko-KR", {
		dateStyle: "medium",
		timeStyle: "short"
	});
}
function oc(e) {
	let t = String(e.directionLabel || "").trim();
	if (t === "중립") return "neutral";
	if (t === "혼재" || t === "변동성") return "warning";
	if (t === "도움" || t === "부담 완화") return "positive";
	if (t === "부담") return "negative";
	let n = `${e.directionLabel || ""} ${e.directionTone || ""}`.toLowerCase();
	return /neutral|중립/.test(n) ? "neutral" : /mixed|conflicted|혼재|변동성/.test(n) ? "warning" : /support|positive|완화|호재|긍정|지지|강화|도움/.test(n) ? "positive" : /risk|negative|부담|악화|위험|하방/.test(n) ? "negative" : "neutral";
}
function sc(e) {
	let t = String(e.directionLabel || "").trim();
	return !t || t === "도움" ? "긍정 요인" : t === "부담" ? "부담 가중" : t === "변동성" ? "변동성 증가" : t;
}
function cc(e) {
	let t = (e) => String(e || "").replace(/marketTape와 macroSnapshot가 비어 있어 가격 검증이 약하다\.?/g, "가격·거시 데이터가 아직 충분하지 않아 뉴스 흐름을 숫자로 검증하기 어렵습니다.").replace(/marketTape/g, "가격 데이터").replace(/macroSnapshot/g, "거시 데이터").trim();
	if (typeof e != "string") return {
		title: t(e.title || ""),
		summary: t(e.summary || ""),
		sourceRefs: e.sourceRefs || []
	};
	let n = t(e.trim()), r = n.match(/['"]title['"]:\s*['"]([^'"]+)['"]/)?.[1] || "", i = n.match(/['"]summary['"]:\s*['"]([^'"]+)['"]/)?.[1] || "", a = (n.match(/['"]sourceRefs['"]:\s*\[([^\]]*)\]/)?.[1] || "").split(",").map((e) => e.replace(/['"]/g, "").trim()).filter(Boolean);
	return r || i ? {
		title: r,
		summary: i,
		sourceRefs: a
	} : {
		title: "",
		summary: n,
		sourceRefs: []
	};
}
function lc({ items: e }) {
	return /* @__PURE__ */ (0, K.jsx)("ul", {
		className: "market-state-check-list",
		children: e.slice(0, 5).map((e, t) => {
			let n = cc(e);
			return /* @__PURE__ */ (0, K.jsxs)("li", {
				className: "market-state-check-item",
				children: [
					n.title && /* @__PURE__ */ (0, K.jsx)("strong", { children: n.title }),
					n.summary && /* @__PURE__ */ (0, K.jsx)("span", { children: n.summary }),
					n.sourceRefs.length ? /* @__PURE__ */ (0, K.jsx)("small", { children: n.sourceRefs.join(" · ") }) : null
				]
			}, `${n.title || n.summary}-${t}`);
		})
	});
}
function uc({ driver: e }) {
	let t = ec[e.confidence] || e.confidence || "보통", n = e.interpretation, r = e.marketImpact || e.interpretation, i = e.evidenceSummary || e.whyItMatters || e.rationale, a = e.nextMemoryCheck || e.whatToWatch || e.nextCheckpoint, o = [
		i ? {
			label: "근거 요약",
			value: i
		} : null,
		r && r !== n && r !== i ? {
			label: "시장 영향",
			value: r
		} : null,
		a ? {
			label: "다음 확인",
			value: a
		} : null
	].filter(Boolean);
	return /* @__PURE__ */ (0, K.jsxs)("article", {
		className: `market-driver-card momentum-${e.momentum || "stable"}`,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "market-driver-top",
				children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: e.title }), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "market-driver-chip-row",
					children: e.directionLabel && /* @__PURE__ */ (0, K.jsx)("span", {
						className: `market-direction-chip direction-${oc(e)}`,
						children: sc(e)
					})
				})]
			}),
			n && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "market-driver-summary",
				children: n
			}),
			o.length ? /* @__PURE__ */ (0, K.jsxs)("details", {
				className: "market-driver-details",
				children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "근거 보기" }), /* @__PURE__ */ (0, K.jsx)("dl", {
					className: "market-driver-detail-list",
					children: o.map((e) => /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: e.label }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e.value })] }, e.label))
				})]
			}) : null,
			/* @__PURE__ */ (0, K.jsxs)("footer", { children: [/* @__PURE__ */ (0, K.jsxs)("small", { children: [
				"확신도 ",
				t,
				e.confidencePct ? ` · ${e.confidencePct}%` : ""
			] }), /* @__PURE__ */ (0, K.jsx)("button", {
				type: "button",
				className: "btn btn--icon agent-action agent-ask-btn",
				"data-tooltip": "Agent에게 묻기",
				"aria-label": "Agent에게 묻기",
				onClick: () => nt({ message: e.askAgentPrompt }),
				children: /* @__PURE__ */ (0, K.jsx)("span", {
					className: "agent-logo-slot",
					"aria-hidden": "true"
				})
			})] })
		]
	});
}
var dc = {
	current: "현재",
	stale: "업데이트 필요",
	fallback: "참고용 대체 상태",
	empty: "상태 없음"
}, fc = {
	snapshot: "Market State 스냅샷",
	state_fallback: "기존 중기 내러티브 참고값",
	none: "사용 가능한 상태 없음"
}, pc = {
	within_window: "최신 자료 기준과 생성 시각이 유효 범위 안에 있습니다.",
	new_relevant_evidence: "스냅샷 이후 새 외부 자료가 들어왔습니다. 갱신 전 판단은 현재 투자 자세로 사용하지 않습니다.",
	age_exceeded: "생성 후 72시간이 지나 최신성이 만료됐습니다.",
	update_failed: "최근 업데이트가 실패해 현재 상태로 확정할 수 없습니다.",
	invalid_as_of: "기준 시각이 없거나 올바르지 않아 현재 상태로 사용할 수 없습니다.",
	future_as_of: "기준 시각이 현재보다 미래여서 검증이 필요합니다.",
	missing_input_watermark: "입력 자료 기준점이 없어 최신성을 확인할 수 없습니다.",
	state_fallback: "정식 스냅샷이 없어 기존 중기 내러티브를 참고용으로만 보여줍니다.",
	no_state: "아직 생성된 시장 상태가 없습니다."
};
function mc(e) {
	if (!e?.asOf || !e.resolvedAt) return "계산 불가";
	let t = new Date(e.asOf).getTime(), n = new Date(e.resolvedAt).getTime();
	if (!Number.isFinite(t) || !Number.isFinite(n) || n < t) return "계산 불가";
	let r = Math.floor((n - t) / 6e4);
	if (r < 60) return `${r}분`;
	let i = Math.floor(r / 60);
	return i < 48 ? `${i}시간` : `${Math.floor(i / 24)}일 ${i % 24}시간`;
}
function hc({ stateRef: e }) {
	let t = e?.freshnessReason === "age_exceeded" ? "만료" : e ? dc[e.status] : "확인 불가";
	return /* @__PURE__ */ (0, K.jsxs)("dl", {
		className: "market-state-meta",
		"aria-label": "시장 상태 기준 정보",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "상태" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: t })] }),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				"data-qa": "market-state-asof",
				children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "기준 시각" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: ac(e?.asOf || void 0) || "없음" })]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "경과" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: mc(e) })] }),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				"data-qa": "market-state-source",
				children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "출처" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e ? fc[e.sourceKind] : "응답 검증 실패" })]
			}),
			e ? /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: "범위" }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e.scope })] }) : null
		]
	});
}
function gc({ stateRef: e }) {
	let t = e.freshnessReason === "age_exceeded", n = e.freshnessReason === "new_relevant_evidence" ? "새 외부 자료가 들어왔습니다." : pc[e.freshnessReason] || "최신성을 다시 확인해야 합니다.", r = e.freshnessReason === "new_relevant_evidence" ? ac(e.relevantEvidenceWatermark || void 0) : "";
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "market-state-stale-notice",
		"data-qa": "market-state-stale-notice",
		role: "status",
		"aria-live": "polite",
		children: [
			/* @__PURE__ */ (0, K.jsx)("strong", { children: t ? "최신성 만료" : "업데이트 필요" }),
			/* @__PURE__ */ (0, K.jsxs)("span", { children: [n, " 이전 스냅샷을 표시 중입니다."] }),
			r ? /* @__PURE__ */ (0, K.jsxs)("time", {
				dateTime: e.relevantEvidenceWatermark || void 0,
				children: ["새 자료 기준 ", r]
			}) : null
		]
	});
}
function _c({ state: e, stateRef: t, error: n, drivers: r }) {
	let i = e === "fallback" ? "참고용 내러티브만 있습니다" : "아직 생성된 시장 상태가 없습니다", a = n ? `시장 상태 응답을 사용할 수 없습니다: ${n}` : pc[t?.freshnessReason || ""] || "현재 상태를 검증할 수 없습니다. 업데이트 후 다시 확인하세요.";
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: `market-state-gap state-${e}`,
		role: "status",
		children: [
			/* @__PURE__ */ (0, K.jsx)("span", { children: dc[e] }),
			/* @__PURE__ */ (0, K.jsx)("h3", { children: i }),
			/* @__PURE__ */ (0, K.jsx)("p", { children: a }),
			e === "fallback" && r.length ? /* @__PURE__ */ (0, K.jsxs)("p", { children: [
				"기존 내러티브 ",
				r.length,
				"건은 탐색 단서일 뿐, 현재 투자 판단으로 사용하지 마세요."
			] }) : null
		]
	});
}
function vc({ payload: e, selectedMarket: t = "overall", loading: n = !1, updating: r = !1, updateDisabled: i = !1, error: a = "", onSelectMarket: o, onUpdate: s, onReload: c }) {
	let l = ls(e), u = l?.status || "empty", d = e?.marketViews || {}, { isSelected: f } = vn(), p = tc.filter((e) => e === "overall" || !!d[e] && f(e)), m = p.includes(t) ? t : "overall", h = m === "overall" ? d.overall || e : d[m] || e, g = h?.drivers ?? [], _ = h?.plainConclusion || h?.summary || "", v = h?.reasonSummary || h?.sourceSummary || h?.stance || "", y = ic(v), b = u === "current" || u === "stale", x = h?.briefs?.length ? h.briefs : [
		{
			label: "현재 판단",
			value: _
		},
		{
			label: "시장 해석",
			value: v
		},
		{
			label: "행동 가이드",
			value: h?.actionGuide?.action || h?.stance || ""
		},
		{
			label: "다음 확인",
			value: h?.actionGuide?.timing || (h?.watchItems || []).slice(0, 3).join("; ")
		}
	].filter((e) => e.value);
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: `market-state-surface market-state-surface-${u}`,
		"data-qa": `market-state-${u}`,
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "market-state-head",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
					className: "section-kicker",
					children: "Market State"
				}), /* @__PURE__ */ (0, K.jsx)("h2", { children: h?.title || e?.title || "현재 중기 시장 상황" })] }), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "market-state-head-actions",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "button",
						"data-qa": "market-state-update",
						onClick: s,
						disabled: !s || i || r || n,
						children: r ? "업데이트 중" : u === "current" ? "시장 메모리 업데이트" : "시장 상태 업데이트"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: c,
						disabled: !c || n || r,
						children: n ? "불러오는 중…" : "새로고침"
					})]
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)(hc, { stateRef: l }),
			u === "stale" && l ? /* @__PURE__ */ (0, K.jsx)(gc, { stateRef: l }) : null,
			b && p.length > 1 ? /* @__PURE__ */ (0, K.jsx)("div", {
				className: "segment market-scope-tabs",
				role: "group",
				"aria-label": "시장 범위 선택",
				children: p.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					"aria-pressed": m === e,
					onClick: () => o?.(e),
					children: nc[e]
				}, e))
			}) : null,
			b ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
				u === "current" ? /* @__PURE__ */ (0, K.jsx)("p", {
					className: "market-state-current-note",
					children: pc[l?.freshnessReason || "within_window"]
				}) : null,
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "market-state-overview",
					"data-qa": "market-state-posture",
					children: [v ? /* @__PURE__ */ (0, K.jsxs)("section", {
						className: "market-state-interpretation",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", { children: "시장 해석" }),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: y.lead }),
							y.support ? /* @__PURE__ */ (0, K.jsx)("p", { children: y.support }) : null
						]
					}) : null, h?.actionGuide || h?.posture || _ ? /* @__PURE__ */ (0, K.jsxs)("section", {
						className: `market-state-posture posture-${h?.posture?.tone || "watch"}`,
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", { children: "판단 및 투자 행동" }),
							_ && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "market-state-summary",
								children: _
							}),
							h?.actionGuide ? /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "market-state-action-body",
								children: [
									/* @__PURE__ */ (0, K.jsx)("strong", { children: h.actionGuide.headline }),
									/* @__PURE__ */ (0, K.jsx)("p", { children: h.actionGuide.action }),
									h.actionGuide.timing && /* @__PURE__ */ (0, K.jsx)("small", { children: h.actionGuide.timing })
								]
							}) : h?.posture ? /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "market-state-action-body",
								children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: h.posture.label }), /* @__PURE__ */ (0, K.jsx)("p", { children: h.posture.summary })]
							}) : null,
							h?.watchItems?.length || x[3]?.value ? /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "market-state-action-list",
								children: [/* @__PURE__ */ (0, K.jsx)("b", { children: "다음 확인" }), h?.watchItems?.length ? /* @__PURE__ */ (0, K.jsx)("ul", { children: h.watchItems.slice(0, 3).map((e) => /* @__PURE__ */ (0, K.jsx)("li", { children: e }, e)) }) : /* @__PURE__ */ (0, K.jsx)("p", { children: x[3]?.value })]
							}) : null
						]
					}) : null]
				}),
				/* @__PURE__ */ (0, K.jsx)("div", {
					className: "market-state-drivers",
					"data-qa": "market-state-drivers",
					children: g.map((e, t) => /* @__PURE__ */ (0, K.jsx)(uc, { driver: e }, e.id || t))
				}),
				h && ((h.counterEvidence?.length || 0) > 0 || (h.uncertainties?.length || 0) > 0) ? /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "market-state-checks",
					"aria-label": "반대 근거와 불확실성",
					children: [h.counterEvidence?.length ? /* @__PURE__ */ (0, K.jsxs)("section", {
						"data-qa": "market-state-counter-evidence",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "반대 근거" }), /* @__PURE__ */ (0, K.jsx)(lc, { items: h.counterEvidence })]
					}) : null, h.uncertainties?.length ? /* @__PURE__ */ (0, K.jsxs)("section", {
						"data-qa": "market-state-uncertainties",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "불확실성" }), /* @__PURE__ */ (0, K.jsx)(lc, { items: h.uncertainties })]
					}) : null]
				}) : null,
				h?.watchItems?.length || x[3]?.value ? /* @__PURE__ */ (0, K.jsxs)("section", {
					className: "market-state-next-checks",
					"data-qa": "market-state-next-checks",
					children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "다음 확인" }), /* @__PURE__ */ (0, K.jsx)("ul", { children: (h?.watchItems || [x[3]?.value]).filter(Boolean).slice(0, 5).map((e) => /* @__PURE__ */ (0, K.jsx)("li", { children: e }, e)) })]
				}) : null
			] }) : /* @__PURE__ */ (0, K.jsx)(_c, {
				state: u,
				stateRef: l,
				error: a,
				drivers: g
			}),
			b && e?.sourceRefs?.length ? /* @__PURE__ */ (0, K.jsxs)("details", {
				className: "market-state-sources",
				children: [/* @__PURE__ */ (0, K.jsxs)("summary", { children: [
					"사용한 출처 ",
					e.sourceRefs.length,
					"개"
				] }), /* @__PURE__ */ (0, K.jsx)("ul", { children: e.sourceRefs.slice(0, 8).map((e, t) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [e.url ? /* @__PURE__ */ (0, K.jsx)("a", {
					href: e.url,
					target: "_blank",
					rel: "noreferrer",
					children: e.title || e.source || e.url
				}) : /* @__PURE__ */ (0, K.jsx)("span", { children: e.title || e.source || e.id }), e.source && /* @__PURE__ */ (0, K.jsx)("small", { children: e.source })] }, e.id || t)) })]
			}) : null
		]
	});
}
function yc({ onUpdate: e, updating: t = !1, updateDisabled: n = !1, onContext: r } = {}) {
	let [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)("overall"), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)(!1), p = (0, l.useCallback)(async () => {
		f(!0), u("");
		try {
			let e = await B("/api/memory/state-dashboard?limit=5");
			a(e);
			let t = us(e);
			yn().updateAgentContext?.({
				surface: "market_state",
				viewId: "memory",
				reportKind: "",
				reportId: "",
				marketState: t
			}), r?.(t);
		} catch (e) {
			a(null), u(e instanceof Error ? e.message : String(e)), r?.(null);
		} finally {
			f(!1);
		}
	}, [r]);
	return (0, l.useEffect)(() => {
		p();
	}, [p]), (0, l.useEffect)(() => {
		yn().applyAgentBranding?.();
	}, [i]), /* @__PURE__ */ (0, K.jsx)(vc, {
		payload: i,
		selectedMarket: o,
		loading: d,
		updating: t,
		updateDisabled: n,
		error: c,
		onSelectMarket: s,
		onUpdate: e,
		onReload: p
	});
}
//#endregion
//#region src/app/marketMemoryJobResume.ts
var bc = "folio.marketMemory.activeJob.v1", xc = /^job_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, Sc = /* @__PURE__ */ new Set([
	"queued",
	"running",
	"cancel_requested",
	"committing",
	"done",
	"cancelled",
	"failed",
	"failed_cancel",
	"failed_commit",
	"failed_restart",
	"failed_commit_recovery"
]), Cc = "market_memory_update", wc = "LLM CLI 시장 메모리 업데이트";
function Tc() {
	try {
		return typeof window > "u" ? null : window.localStorage;
	} catch {
		return null;
	}
}
function Ec(e) {
	return typeof e == "string" && xc.test(e);
}
function Dc(e, t) {
	if (!e || typeof e != "object" || Array.isArray(e)) return !1;
	let n = e;
	return n.id === t && Sc.has(n.status);
}
function Oc(e) {
	if (!e || typeof e != "object" || Array.isArray(e)) return !1;
	let t = e;
	return !Ec(t.id) || !Sc.has(t.status) || !I(t.status) ? !1 : t.taskType === Cc || t.taskType === void 0 && t.label === wc;
}
function kc(e = Tc()) {
	try {
		e?.removeItem(bc);
	} catch {}
}
function Ac(e = Tc()) {
	let t = null;
	try {
		t = e?.getItem("folio.marketMemory.activeJob.v1") ?? null;
	} catch {
		return null;
	}
	return t ? Ec(t) ? t : (kc(e), null) : null;
}
function jc(e, t = Tc()) {
	if (!Ec(e) || !t) return !1;
	try {
		return t.setItem(bc, e), t.getItem(bc) === e;
	} catch {
		return !1;
	}
}
async function Mc(e, t = Tc()) {
	let n = Ac(t);
	if (!n) return { kind: "none" };
	let r;
	try {
		r = await e(n);
	} catch {
		return {
			kind: "unavailable",
			id: n
		};
	}
	return Dc(r, n) ? I(r.status) ? {
		kind: "active",
		job: r
	} : (kc(t), {
		kind: "terminal",
		job: r
	}) : (kc(t), { kind: "invalid" });
}
async function Nc(e, t = Tc()) {
	let n;
	try {
		n = await e();
	} catch {
		return { kind: "none" };
	}
	if (!Array.isArray(n)) return { kind: "invalid" };
	let r = n.find(Oc);
	return r ? (jc(r.id, t), {
		kind: "active",
		job: r
	}) : { kind: "none" };
}
//#endregion
//#region src/app/MarketMemoryRoute.tsx
function Pc() {
	return (/* @__PURE__ */ new Date()).toISOString().slice(0, 10);
}
function Fc(e) {
	return e.snapshot?.headline ? e.message || `시장 상태 스냅샷을 저장했습니다: ${e.snapshot.headline}` : e.snapshotId || e.title ? e.message || `시장 상태 스냅샷을 저장했습니다${e.title ? `: ${e.title}` : ""}` : `${e.message || (e.ok ? "시장 내러티브를 정리했습니다." : "시장 내러티브 정리가 완료되었습니다.")}${Number.isFinite(Number(e.savedCount)) ? ` 저장 ${e.savedCount}건` : ""}${e.estimatedInputTokens ? ` · 입력 약 ${e.estimatedInputTokens} tokens` : ""}${e.rawEntryCount === void 0 ? "" : ` · 응답 ${e.rawEntryCount}건 · 제외 ${e.droppedCount || 0}건`}`;
}
function Ic(e) {
	let t = e;
	return !!(t?.id && t.status);
}
async function Lc() {
	return V("/api/memory/update", { date: Pc() });
}
function Rc() {
	let [e, t] = (0, l.useState)(0), n = fn("marketMemory"), [r, i] = (0, l.useState)(!1), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(""), [u, d] = (0, l.useState)(() => {
		let e = Ac();
		return e ? {
			id: e,
			status: "running"
		} : null;
	}), f = (0, l.useRef)(null), p = (0, l.useCallback)((e) => {
		Qe("market-memory", {
			surface: "market_state",
			viewId: "memory",
			reportKind: "",
			reportId: "",
			marketState: e
		});
	}, []);
	function m(e) {
		if (e.ok === !1) throw Error(e.message || e.status || "시장 메모리 업데이트에 실패했습니다.");
		kc(), o(`시장 메모리를 업데이트했습니다. ${Fc(e)}`), d(null), t((e) => e + 1);
	}
	(0, l.useEffect)(() => {
		let e = !0;
		return (async () => {
			let t = await Mc((e) => B(`/api/jobs/${encodeURIComponent(e)}`));
			if (t.kind === "none" && (t = await Nc(() => B("/api/jobs"))), e) if (t.kind === "active") {
				d(t.job), i(!0), o("이전에 시작한 서버 작업에 자동으로 다시 연결했습니다.");
				try {
					await h(t.job);
				} catch (t) {
					if (!e) return;
					t instanceof ot ? (kc(), d(null), c(t.message), o("")) : t instanceof DOMException && t.name === "AbortError" || (c(t instanceof Error ? t.message : "작업 상태 확인에 실패했습니다."), o(""));
				} finally {
					e && i(!1);
				}
			} else t.kind === "terminal" ? (d(null), t.job.status === "done" ? m(t.job.result || {}) : c(t.job.message || t.job.error || "이전 시장 메모리 작업이 종료되었습니다.")) : t.kind === "unavailable" ? (d({
				id: t.id,
				status: "running"
			}), o("저장된 시장 메모리 작업의 상태를 다시 확인해야 합니다.")) : t.kind === "invalid" && (d(null), c("저장된 시장 메모리 작업 정보를 확인할 수 없어 안전하게 제거했습니다."));
		})(), () => {
			e = !1, f.current?.abort();
		};
	}, []);
	async function h(e) {
		f.current?.abort();
		let t = new AbortController();
		f.current = t;
		try {
			m((await dt(e, { signal: t.signal })).result || {});
		} finally {
			f.current === t && (f.current = null);
		}
	}
	async function g() {
		i(!0), c(""), o("AI Agent가 단기 뉴스와 기존 중기 메모리를 업데이트하는 중입니다.");
		try {
			o("시장 메모리와 화면용 시장 상태를 함께 갱신하는 중입니다.");
			let e = await Lc();
			Ic(e) ? (jc(e.id), d(e), await h(e)) : m(e);
		} catch (e) {
			e instanceof ot ? (kc(), d(null), c(e.message), o("")) : e instanceof DOMException && e.name === "AbortError" || (c(e instanceof Error ? e.message : "시장 메모리 업데이트에 실패했습니다."), o(""));
		} finally {
			i(!1);
		}
	}
	async function _() {
		if (u) {
			i(!0), c(""), o("같은 시장 메모리 작업의 상태를 다시 확인하는 중입니다.");
			try {
				await h(u);
			} catch (e) {
				e instanceof ot ? (kc(), d(null), c(e.message), o("")) : e instanceof DOMException && e.name === "AbortError" || (c(e instanceof Error ? e.message : "작업 상태 확인에 실패했습니다."), o(""));
			} finally {
				i(!1);
			}
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-market-memory-route",
		"data-market-memory-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Market Memory",
				title: "시장 내러티브",
				description: "단기 뉴스 흐름을 중기 시장 상황으로 압축해 투자 판단의 배경으로 유지합니다."
			}),
			s && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: s
			}),
			a && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				children: a
			}),
			u && !r ? /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-dashboard-warning market-state-job-resume",
				"data-qa": "market-state-job-still-running",
				role: "status",
				children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [
					"작업 ",
					u.id,
					" · 서버에서 계속 실행 중"
				] }), /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					"data-qa": "market-state-job-resume",
					onClick: () => void _(),
					children: "같은 작업 다시 확인"
				})]
			}) : null,
			/* @__PURE__ */ (0, K.jsx)(ln, { mode: "market-memory" }),
			/* @__PURE__ */ (0, K.jsx)("section", {
				className: "market-state-dashboard react-market-memory-dashboard",
				"aria-label": "현재 중기 시장 상황",
				children: /* @__PURE__ */ (0, K.jsx)(yc, {
					onUpdate: g,
					updating: r,
					updateDisabled: !!u,
					onContext: p
				}, `${e}:${n}`)
			})
		]
	});
}
//#endregion
//#region src/app/portfolio/HoldingsTable.tsx
function zc({ positions: e, onChange: t }) {
	let [n, r] = (0, l.useState)({});
	function i(n, r, i) {
		t(e.map((e, t) => t === n ? {
			...e,
			[r]: i
		} : e));
	}
	function a(n) {
		t(e.filter((e, t) => t !== n)), r((e) => {
			let t = {};
			for (let [r, i] of Object.entries(e)) {
				let e = Number(r);
				e < n ? t[e] = i : e > n && (t[e - 1] = i);
			}
			return t;
		});
	}
	async function o(n, i) {
		let a = i.trim();
		if (!a) {
			r((e) => ({
				...e,
				[n]: ""
			}));
			return;
		}
		try {
			let i = await B(`/api/company/resolve?q=${encodeURIComponent(a)}&limit=1`);
			if (i.status !== "confident" || !i.match) {
				r((e) => ({
					...e,
					[n]: ""
				}));
				return;
			}
			let o = i.match;
			r((e) => ({
				...e,
				[n]: o.name
			}));
			let s = {};
			o.ticker && o.ticker !== a && (s.ticker = o.ticker), o.market && !e[n]?.market && (s.market = o.market), Object.keys(s).length && t(e.map((e, t) => t === n ? {
				...e,
				...s
			} : e));
		} catch {
			r((e) => ({
				...e,
				[n]: ""
			}));
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "portfolio-holdings-table-wrap",
		children: [/* @__PURE__ */ (0, K.jsxs)("table", {
			className: "portfolio-holdings-table",
			children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, K.jsx)("th", { children: "종목" }),
				/* @__PURE__ */ (0, K.jsx)("th", { children: "수량" }),
				/* @__PURE__ */ (0, K.jsx)("th", { children: "평균단가" }),
				/* @__PURE__ */ (0, K.jsx)("th", { children: "시장" }),
				/* @__PURE__ */ (0, K.jsx)("th", { children: /* @__PURE__ */ (0, K.jsx)("span", {
					className: "sr-only",
					children: "삭제"
				}) })
			] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: e.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, K.jsxs)("td", { children: [/* @__PURE__ */ (0, K.jsx)("input", {
					"aria-label": `${t + 1}번 종목`,
					value: e.ticker,
					onChange: (e) => i(t, "ticker", e.currentTarget.value.toUpperCase()),
					onBlur: (e) => void o(t, e.currentTarget.value),
					placeholder: "NVDA / 삼성전자"
				}), n[t] && /* @__PURE__ */ (0, K.jsx)("small", {
					className: "holdings-resolved",
					children: n[t]
				})] }),
				/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("input", {
					"aria-label": `${e.ticker || t + 1} 수량`,
					value: e.quantity,
					onChange: (e) => i(t, "quantity", e.currentTarget.value),
					inputMode: "decimal"
				}) }),
				/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("input", {
					"aria-label": `${e.ticker || t + 1} 평균단가`,
					value: e.averagePrice ?? "",
					onChange: (e) => i(t, "averagePrice", e.currentTarget.value),
					inputMode: "decimal"
				}) }),
				/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("input", {
					"aria-label": `${e.ticker || t + 1} 시장`,
					value: e.market || "",
					onChange: (e) => i(t, "market", e.currentTarget.value.toUpperCase()),
					placeholder: "US / KR / EUROPE / JP"
				}) }),
				/* @__PURE__ */ (0, K.jsx)("td", { children: /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					className: "btn",
					onClick: () => a(t),
					children: "삭제"
				}) })
			] }, t)) })]
		}), !e.length && /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "cockpit-empty",
			children: [
				"등록된 보유 종목이 없습니다. ",
				/* @__PURE__ */ (0, K.jsx)("strong", { children: "종목 추가" }),
				"를 눌러 직접 입력하세요 — 이름으로 적어도 종목 코드로 바꿔 줍니다."
			]
		})]
	});
}
//#endregion
//#region src/app/agentWorkspace/openScopedThread.ts
function Bc(e) {
	window.dispatchEvent(new CustomEvent("folio:open-agent-thread", { detail: e })), nt({});
}
//#endregion
//#region src/app/portfolio/ConsultationEntry.tsx
function Vc({ tickers: e }) {
	return /* @__PURE__ */ (0, K.jsx)("button", {
		className: "btn btn--primary",
		type: "button",
		onClick: () => Bc({
			title: "포트폴리오 대화",
			scope: {
				kind: "portfolio",
				id: "current",
				tickers: e
			},
			initialMessage: "현재 Portfolio와 최근 뉴스·브리핑·시장 내러티브를 연결해 우선 확인할 변화와 반대 근거를 검토해줘."
		}),
		children: "포트폴리오 짚어보기"
	});
}
//#endregion
//#region src/app/portfolio/portfolioTypes.ts
function Hc(e) {
	return !!(e && e.type === "comparison");
}
function Uc(e, t = 0) {
	return e == null || !Number.isFinite(e) ? "—" : e.toLocaleString("ko-KR", {
		maximumFractionDigits: t,
		minimumFractionDigits: t
	});
}
function Wc(e, t = 1) {
	return e == null || !Number.isFinite(e) ? "—" : `${(e * 100).toFixed(t)}%`;
}
function Gc(e) {
	return e == null || !Number.isFinite(e) || e === 0 ? "flat" : e > 0 ? "up" : "down";
}
//#endregion
//#region src/app/portfolio/PortfolioAnalysis.tsx
var Kc = [
	{
		key: "marketWeights",
		label: "시장"
	},
	{
		key: "sectorWeights",
		label: "섹터"
	},
	{
		key: "currencyWeights",
		label: "통화"
	},
	{
		key: "assetClassWeights",
		label: "자산군"
	}
];
function qc({ slices: e }) {
	return e.length ? /* @__PURE__ */ (0, K.jsx)("ul", {
		className: "portfolio-weights",
		children: e.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", {
			className: "portfolio-weight",
			children: [
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "portfolio-weight__head",
					children: [/* @__PURE__ */ (0, K.jsx)("span", {
						className: "portfolio-weight__label",
						children: e.label
					}), /* @__PURE__ */ (0, K.jsx)("span", {
						className: "portfolio-weight__value",
						children: Wc(e.weight)
					})]
				}),
				/* @__PURE__ */ (0, K.jsx)("div", {
					className: "portfolio-weight__track",
					role: "img",
					"aria-label": `${e.label} 비중 ${Wc(e.weight)}`,
					children: /* @__PURE__ */ (0, K.jsx)("span", {
						className: "portfolio-weight__fill",
						style: { inlineSize: `${Math.min(100, e.weight * 100)}%` }
					})
				}),
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "portfolio-weight__foot",
					children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [
						e.positions,
						"종목 · USD ",
						Uc(e.marketValue)
					] }), /* @__PURE__ */ (0, K.jsx)("span", {
						"data-sign": Gc(e.pnl),
						children: Wc(e.pnlPct)
					})]
				})
			]
		}, e.label))
	}) : /* @__PURE__ */ (0, K.jsx)("p", {
		className: "portfolio-empty",
		children: "계산할 수 있는 자료가 없습니다."
	});
}
function Jc({ revision: e }) {
	let [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)("marketWeights"), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(!0);
	if ((0, l.useEffect)(() => {
		let e = !1;
		return c(!0), (async () => {
			try {
				let t = await B("/api/portfolio/analytics");
				e || (n(t), o(""));
			} catch (t) {
				e || o(t instanceof Error ? t.message : "평가 정보를 불러오지 못했습니다.");
			} finally {
				e || c(!1);
			}
		})(), () => {
			e = !0;
		};
	}, [e]), s && !t) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "portfolio-empty",
		children: "시세를 확인하는 중입니다."
	});
	if (a) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "react-dashboard-error",
		role: "alert",
		children: a
	});
	if (!t) return null;
	let { analytics: u } = t;
	if (!u.totalMarketValue && !t.positions.length) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "portfolio-empty",
		children: "보유 종목을 입력하면 평가액·비중·집중도가 여기에 표시됩니다."
	});
	let d = t.baseCurrency || "USD", f = t.summary.filter((e) => e.currency !== `${d} 기준`);
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "portfolio-analysis",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-metrics",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-metric",
						children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [
							"평가액 (",
							d,
							" 환산)"
						] }), /* @__PURE__ */ (0, K.jsx)("strong", { children: Uc(u.totalMarketValue) })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-metric",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "원금" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: Uc(u.totalCost) })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-metric",
						"data-sign": Gc(u.totalPnl),
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", { children: "평가손익" }),
							/* @__PURE__ */ (0, K.jsx)("strong", { children: Uc(u.totalPnl) }),
							/* @__PURE__ */ (0, K.jsx)("small", { children: Wc(u.totalPnlPct) })
						]
					})
				]
			}),
			(f.length > 1 || t.cash.length > 0) && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsx)("h3", { children: "통화별" }),
					/* @__PURE__ */ (0, K.jsxs)("table", {
						className: "portfolio-mini-table",
						children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
							/* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: "통화"
							}),
							/* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: "평가액"
							}),
							/* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: "손익"
							}),
							/* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: "현금"
							})
						] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: f.map((e) => {
							let n = t.cash.find((t) => t.currency === e.currency);
							return /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "row",
									children: e.currency
								}),
								/* @__PURE__ */ (0, K.jsx)("td", { children: Uc(e.marketValue) }),
								/* @__PURE__ */ (0, K.jsxs)("td", {
									"data-sign": Gc(e.pnl),
									children: [
										Uc(e.pnl),
										" ",
										/* @__PURE__ */ (0, K.jsx)("small", { children: Wc(e.pnlPct) })
									]
								}),
								/* @__PURE__ */ (0, K.jsx)("td", { children: n ? Uc(n.amount) : "—" })
							] }, e.currency);
						}) })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						className: "portfolio-note",
						children: [
							"현금은 평가액 합계에 포함하지 않습니다. 환율:",
							" ",
							Object.entries(t.fxRates).filter(([e]) => e !== "USD").map(([e, t]) => `${e} ${(1 / t.rateToUsd).toFixed(1)}/USD`).join(" · ") || "—"
						]
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "portfolio-block__head",
					children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "구성" }), /* @__PURE__ */ (0, K.jsx)("div", {
						className: "segment",
						role: "group",
						"aria-label": "구성 기준",
						children: Kc.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
							type: "button",
							"aria-pressed": r === e.key,
							onClick: () => i(e.key),
							children: e.label
						}, e.key))
					})]
				}), /* @__PURE__ */ (0, K.jsx)(qc, { slices: u[r] })]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "집중도" }), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "portfolio-metrics portfolio-metrics--compact",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "portfolio-metric",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "보유 종목" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: u.concentration.holdings })]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "portfolio-metric",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "최대 1종목" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: Wc(u.concentration.top1) })]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "portfolio-metric",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "상위 3종목" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: Wc(u.concentration.top3) })]
						})
					]
				})]
			}),
			u.comments.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsx)("h3", { children: "살펴볼 점" }),
					/* @__PURE__ */ (0, K.jsx)("ul", {
						className: "portfolio-comments",
						children: u.comments.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", {
							className: "portfolio-comment surface",
							"data-level": e.level,
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.title }), /* @__PURE__ */ (0, K.jsx)("p", { children: e.body })]
						}, e.title))
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-note",
						children: "규칙으로 계산한 관찰입니다. 매수·매도 권유가 아닙니다."
					})
				]
			})
		]
	});
}
//#endregion
//#region src/app/portfolio/PortfolioBacktest.tsx
var Yc = [
	{
		id: "none",
		label: "안 함"
	},
	{
		id: "monthly",
		label: "매월"
	},
	{
		id: "quarterly",
		label: "분기"
	},
	{
		id: "yearly",
		label: "매년"
	}
], Xc = [
	{
		key: "totalReturn",
		label: "총 수익률",
		kind: "pct"
	},
	{
		key: "cagr",
		label: "연평균(CAGR)",
		kind: "pct"
	},
	{
		key: "maxDrawdown",
		label: "최대 낙폭",
		kind: "pct"
	},
	{
		key: "volatility",
		label: "변동성",
		kind: "pct"
	},
	{
		key: "sharpe",
		label: "샤프",
		kind: "num"
	},
	{
		key: "benchmarkTotalReturn",
		label: "벤치마크 수익률",
		kind: "pct"
	}
];
function Zc({ series: e, benchmark: t }) {
	if (e.length < 2) return null;
	let n = [...e.map((e) => e.value), ...(t || []).map((e) => e.value)], r = Math.min(...n), i = Math.max(...n) - r || 1, a = (e) => e.map((t, n) => {
		let a = n / (e.length - 1) * 640, o = 160 - (t.value - r) / i * 160;
		return `${n === 0 ? "M" : "L"}${a.toFixed(1)},${o.toFixed(1)}`;
	}).join(" ");
	return /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "portfolio-sparkline",
		viewBox: "0 0 640 160",
		preserveAspectRatio: "none",
		role: "img",
		"aria-label": `평가액 추이 ${e[0].date}부터 ${e[e.length - 1].date}까지`,
		children: [t && t.length > 1 && /* @__PURE__ */ (0, K.jsx)("path", {
			className: "portfolio-sparkline__benchmark",
			d: a(t)
		}), /* @__PURE__ */ (0, K.jsx)("path", {
			className: "portfolio-sparkline__line",
			d: a(e)
		})]
	});
}
function Qc({ revision: e }) {
	let [t, n] = (0, l.useState)([]), [r, i] = (0, l.useState)([]), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)("2020-01-01"), [u, d] = (0, l.useState)(() => (/* @__PURE__ */ new Date()).toISOString().slice(0, 10)), [f, p] = (0, l.useState)("monthly"), [m, h] = (0, l.useState)(null), [g, _] = (0, l.useState)(""), [v, y] = (0, l.useState)(""), [b, x] = (0, l.useState)(""), [S, C] = (0, l.useState)(""), w = (0, l.useCallback)(async () => {
		try {
			let [e, t] = await Promise.all([B("/api/portfolio/presets"), B("/api/portfolio/backtests")]), r = Array.isArray(e) ? e : e.presets || [];
			n(r), o((e) => e || r[0]?.id || ""), i(Array.isArray(t) ? t : t.backtests || []);
		} catch (e) {
			x(e instanceof Error ? e.message : "백테스트 정보를 불러오지 못했습니다.");
		}
	}, []);
	(0, l.useEffect)(() => {
		w();
	}, [w, e]);
	let T = async () => {
		if (a) {
			_("run"), y(""), x("");
			try {
				h(await V("/api/portfolio/backtests", {
					presetId: a,
					start: s,
					end: u,
					rebalance: f
				}));
			} catch (e) {
				x(e instanceof Error ? e.message : "백테스트를 실행하지 못했습니다.");
			} finally {
				_("");
			}
		}
	}, E = async () => {
		if (m) {
			_("save");
			try {
				await V("/api/portfolio/backtests/save", m), await w(), y("결과를 저장했습니다.");
			} catch (e) {
				x(e instanceof Error ? e.message : "저장하지 못했습니다.");
			} finally {
				_("");
			}
		}
	}, D = async (e) => {
		if (S !== e.id) {
			C(e.id);
			return;
		}
		_(e.id);
		try {
			await W(`/api/portfolio/backtests/${encodeURIComponent(e.id)}`, {}), C(""), await w();
		} catch (e) {
			x(e instanceof Error ? e.message : "지우지 못했습니다.");
		} finally {
			_("");
		}
	};
	return t.length ? /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "portfolio-backtest",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsx)("h3", { children: "조건" }),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-backtest-fields",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("label", {
								className: "field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "프리셋" }), /* @__PURE__ */ (0, K.jsx)("select", {
									value: a,
									onChange: (e) => o(e.target.value),
									children: t.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
										value: e.id,
										children: e.name
									}, e.id))
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("label", {
								className: "field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시작" }), /* @__PURE__ */ (0, K.jsx)("input", {
									type: "date",
									value: s,
									onChange: (e) => c(e.target.value)
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("label", {
								className: "field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "종료" }), /* @__PURE__ */ (0, K.jsx)("input", {
									type: "date",
									value: u,
									onChange: (e) => d(e.target.value)
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", {
									id: "rebalanceLabel",
									children: "리밸런싱"
								}), /* @__PURE__ */ (0, K.jsx)("div", {
									className: "segment",
									role: "group",
									"aria-labelledby": "rebalanceLabel",
									children: Yc.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": f === e.id,
										onClick: () => p(e.id),
										children: e.label
									}, e.id))
								})]
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-actions",
						children: [/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							onClick: () => void T(),
							disabled: !!g || s >= u,
							children: g === "run" ? "계산 중" : "백테스트 실행"
						}), s >= u && /* @__PURE__ */ (0, K.jsx)("span", {
							className: "portfolio-note",
							children: "시작일이 종료일보다 앞서야 합니다."
						})]
					})
				]
			}),
			m && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-block__head",
						children: [/* @__PURE__ */ (0, K.jsxs)("h3", { children: [
							m.presetName || m.name,
							" · ",
							m.start,
							" ~ ",
							m.end
						] }), /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn",
							type: "button",
							onClick: () => void E(),
							disabled: !!g,
							children: g === "save" ? "저장 중" : "결과 저장"
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)(Zc, {
						series: m.series,
						benchmark: m.benchmarkSeries
					}),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						className: "portfolio-note",
						children: [
							"진한 선이 이 목표 비중, 옅은 선이 벤치마크(",
							m.benchmark?.ticker || "—",
							")입니다. 둘 다 ",
							Uc(m.initialValue),
							"에서 시작합니다."
						]
					}),
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "portfolio-metrics portfolio-metrics--compact",
						children: Xc.map((e) => {
							let t = m.metrics[e.key];
							return /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "portfolio-metric",
								"data-sign": e.kind === "pct" && e.key !== "volatility" && e.key !== "maxDrawdown" ? Gc(t) : void 0,
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: e.label }), /* @__PURE__ */ (0, K.jsx)("strong", { children: e.kind === "pct" ? Wc(t) : Number.isFinite(t) ? t.toFixed(2) : "—" })]
							}, e.key);
						})
					}),
					m.assetContributions && m.assetContributions.length > 0 && /* @__PURE__ */ (0, K.jsx)("div", {
						className: "portfolio-table-scroll",
						children: /* @__PURE__ */ (0, K.jsxs)("table", {
							className: "portfolio-mini-table",
							children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "종목"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "비중"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "기여"
								})
							] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: m.assetContributions.map((e) => /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "row",
									children: e.name || e.ticker
								}),
								/* @__PURE__ */ (0, K.jsx)("td", { children: Wc(e.weight) }),
								/* @__PURE__ */ (0, K.jsx)("td", {
									"data-sign": Gc(e.contribution),
									children: Wc(e.contribution)
								})
							] }, e.ticker)) })]
						})
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-note",
						children: "리서치용 계산입니다. 과거 가격과 일자별 환율을 쓰며 세금·수수료·체결오차·배당 처리에는 한계가 있습니다. 과거 성과가 앞으로를 보장하지 않습니다."
					})
				]
			}),
			r.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "저장한 결과" }), /* @__PURE__ */ (0, K.jsx)("ul", {
					className: "portfolio-preset-list",
					children: r.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", {
						className: "portfolio-preset surface",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.presetName || e.name }), /* @__PURE__ */ (0, K.jsxs)("small", { children: [
							e.start,
							" ~ ",
							e.end,
							" · 총 ",
							Wc(e.metrics?.totalReturn),
							e.savedAt ? ` · ${e.savedAt.slice(0, 10)}` : ""
						] })] }), /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "portfolio-actions",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn",
								type: "button",
								onClick: () => void B(`/api/portfolio/backtests/${encodeURIComponent(e.id)}`).then(h),
								children: "열기"
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn",
								type: "button",
								onClick: () => void D(e),
								disabled: g === e.id,
								children: g === e.id ? "지우는 중" : S === e.id ? "정말 지울까요?" : "지우기"
							})]
						})]
					}, e.id))
				})]
			}),
			v && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-reader-status",
				role: "status",
				children: v
			}),
			b && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				role: "alert",
				children: b
			})
		]
	}) : /* @__PURE__ */ (0, K.jsxs)("p", {
		className: "portfolio-empty",
		children: [
			"백테스트는 프리셋이 있어야 돌릴 수 있습니다. ",
			/* @__PURE__ */ (0, K.jsx)("strong", { children: "프리셋" }),
			" 탭에서 현재 보유로 프리셋을 만든 뒤 다시 오세요."
		]
	});
}
//#endregion
//#region src/app/portfolio/PresetCompare.tsx
var $c = [
	{
		key: "totalReturn",
		label: "총 수익률",
		kind: "pct",
		better: "high"
	},
	{
		key: "cagr",
		label: "연평균(CAGR)",
		kind: "pct",
		better: "high"
	},
	{
		key: "maxDrawdown",
		label: "최대 낙폭",
		kind: "pct",
		better: "nearZero"
	},
	{
		key: "volatility",
		label: "변동성",
		kind: "pct",
		better: "low"
	},
	{
		key: "sharpe",
		label: "샤프",
		kind: "num",
		better: "high"
	}
], el = [
	"blue",
	"teal",
	"gold",
	"purple",
	"burgundy"
];
function tl(e, t) {
	let n = e.metrics[t];
	return typeof n == "number" && Number.isFinite(n) ? n : null;
}
function nl(e, t) {
	return e === null ? "—" : t === "pct" ? Wc(e) : Uc(e, 2);
}
function rl(e, t) {
	return e.presetName || e.name || `프리셋 ${t + 1}`;
}
function il(e, t, n) {
	let r = e.map((e) => tl(e, t)), i = r.filter((e) => e !== null);
	if (i.length < 2) return null;
	let a = (e) => n === "nearZero" ? -Math.abs(e) : n === "high" ? e : -e, o = Math.max(...i.map(a)), s = r.map((e, t) => e !== null && a(e) === o ? t : -1).filter((e) => e >= 0);
	return s.length === 1 ? s[0] : null;
}
function al(e, t, n, r) {
	let i = t.maxTime - t.minTime || 1, a = t.max - t.min || 1;
	return e.map((e, o) => {
		let s = new Date(e.date).getTime(), c = ((Number.isFinite(s) ? s : t.minTime) - t.minTime) / i * n, l = r - (e.value - t.min) / a * r;
		return `${o === 0 ? "M" : "L"}${c.toFixed(1)},${l.toFixed(1)}`;
	}).join(" ");
}
function ol({ results: e }) {
	let t = e.filter((e) => (e.series || []).length > 1);
	if (!t.length) return null;
	let n = t.flatMap((e) => e.series.map((e) => e.value)), r = t.flatMap((e) => e.series.map((e) => new Date(e.date).getTime())).filter((e) => Number.isFinite(e));
	if (!r.length) return null;
	let i = {
		minTime: Math.min(...r),
		maxTime: Math.max(...r),
		min: Math.min(...n),
		max: Math.max(...n)
	};
	return /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "portfolio-sparkline portfolio-compare-chart",
		viewBox: "0 0 640 180",
		preserveAspectRatio: "none",
		role: "img",
		"aria-label": `프리셋 ${t.length}개의 평가액 추이 비교`,
		children: t.map((e, t) => /* @__PURE__ */ (0, K.jsx)("path", {
			"data-tone": el[t % el.length],
			className: "portfolio-compare-line",
			d: al(e.series, i, 640, 180)
		}, e.presetId || e.name || t))
	});
}
var sl = [
	{
		id: "none",
		label: "안 함"
	},
	{
		id: "monthly",
		label: "매월"
	},
	{
		id: "quarterly",
		label: "분기"
	},
	{
		id: "yearly",
		label: "매년"
	}
];
function cl({ presets: e }) {
	let [t, n] = (0, l.useState)("2020-01-01"), [r, i] = (0, l.useState)(() => (/* @__PURE__ */ new Date()).toISOString().slice(0, 10)), [a, o] = (0, l.useState)("monthly"), [s, c] = (0, l.useState)([]), [u, d] = (0, l.useState)(null), [f, p] = (0, l.useState)(""), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(""), v = e.filter((e) => e.positions.length), y = (e) => {
		c((t) => t.includes(e) ? t.filter((t) => t !== e) : [...t, e]);
	}, b = async () => {
		p("run"), h(""), _("");
		try {
			let e = await V("/api/portfolio/backtests/compare", {
				presetIds: s,
				start: t,
				end: r,
				rebalance: a
			});
			d(Hc(e) ? e : null);
		} catch (e) {
			_(e instanceof Error ? e.message : "비교 백테스트를 실행하지 못했습니다.");
		} finally {
			p("");
		}
	}, x = async () => {
		if (u) {
			p("save");
			try {
				await V("/api/portfolio/backtests/save", u), h("비교 결과를 저장했습니다.");
			} catch (e) {
				_(e instanceof Error ? e.message : "저장하지 못했습니다.");
			} finally {
				p("");
			}
		}
	};
	return v.length < 2 ? /* @__PURE__ */ (0, K.jsx)("p", {
		className: "portfolio-empty",
		children: "비교하려면 비중이 담긴 프리셋이 2개 이상 필요합니다. 위에서 프리셋을 하나 더 만드세요."
	}) : /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "portfolio-compare",
		children: [
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "portfolio-compare-picker",
				role: "group",
				"aria-label": "비교할 프리셋",
				children: v.map((e) => /* @__PURE__ */ (0, K.jsxs)("label", {
					className: "portfolio-compare-option",
					children: [
						/* @__PURE__ */ (0, K.jsx)("input", {
							type: "checkbox",
							checked: s.includes(e.id),
							onChange: () => y(e.id)
						}),
						/* @__PURE__ */ (0, K.jsx)("span", { children: e.name }),
						/* @__PURE__ */ (0, K.jsxs)("small", { children: [e.positions.length, "종목"] })
					]
				}, e.id))
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-backtest-fields",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시작" }), /* @__PURE__ */ (0, K.jsx)("input", {
							type: "date",
							value: t,
							onChange: (e) => n(e.target.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "종료" }), /* @__PURE__ */ (0, K.jsx)("input", {
							type: "date",
							value: r,
							onChange: (e) => i(e.target.value)
						})]
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "field",
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							id: "compareRebalanceLabel",
							children: "리밸런싱"
						}), /* @__PURE__ */ (0, K.jsx)("div", {
							className: "segment",
							role: "group",
							"aria-labelledby": "compareRebalanceLabel",
							children: sl.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"aria-pressed": a === e.id,
								onClick: () => o(e.id),
								children: e.label
							}, e.id))
						})]
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-compare-actions",
				children: [
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "button",
						onClick: () => void b(),
						disabled: s.length < 2 || f === "run",
						children: f === "run" ? "비교하는 중" : `${s.length || 0}개 비교 백테스트`
					}),
					u && /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => void x(),
						disabled: f === "save",
						children: "결과 저장"
					}),
					s.length === 1 && /* @__PURE__ */ (0, K.jsx)("span", {
						className: "section-subtitle",
						children: "두 개 이상 골라야 비교할 수 있습니다."
					})
				]
			}),
			g && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: g
			}),
			m && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "section-subtitle",
				children: m
			}),
			u && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("h3", { children: [
						u.start,
						" ~ ",
						u.end,
						" · ",
						u.baseCurrency,
						" 기준"
					] }),
					/* @__PURE__ */ (0, K.jsx)(ol, { results: u.results }),
					/* @__PURE__ */ (0, K.jsx)("ul", {
						className: "portfolio-compare-legend",
						children: u.results.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("li", { children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "portfolio-compare-dot",
							"data-tone": el[t % el.length],
							"aria-hidden": "true"
						}), rl(e, t)] }, e.presetId || e.name || t))
					}),
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "table-scroll",
						children: /* @__PURE__ */ (0, K.jsxs)("table", {
							className: "portfolio-compare-table",
							children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [/* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: "지표"
							}), u.results.map((e, t) => /* @__PURE__ */ (0, K.jsx)("th", {
								scope: "col",
								children: rl(e, t)
							}, e.presetId || e.name || t))] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: $c.map((e) => {
								let t = il(u.results, e.key, e.better);
								return /* @__PURE__ */ (0, K.jsxs)("tr", { children: [/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "row",
									children: e.label
								}), u.results.map((n, r) => {
									let i = tl(n, e.key);
									return /* @__PURE__ */ (0, K.jsx)("td", {
										"data-best": r === t ? "true" : void 0,
										"data-sign": e.kind === "pct" && i !== null ? Gc(i) : void 0,
										children: nl(i, e.kind)
									}, n.presetId || n.name || r);
								})] }, e.key);
							}) })]
						})
					}),
					u.errors?.length ? /* @__PURE__ */ (0, K.jsxs)("p", {
						className: "react-dashboard-warning",
						children: [u.errors.map((e) => e.presetName || e.presetId).join(", "), "는 백테스트에 실패해 표에서 빠졌습니다."]
					}) : null,
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-subtitle",
						children: "리서치용입니다. 과거 가격과 일자별 환율로 계산하며 세금·수수료·체결오차·배당 처리에 한계가 있습니다. 어느 쪽이 나았다는 것이 매수·매도 지시는 아닙니다."
					})
				]
			})
		]
	});
}
//#endregion
//#region src/app/portfolio/PortfolioTargets.tsx
function ll({ revision: e, onChanged: t }) {
	let [n, r] = (0, l.useState)([]), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)(""), [p, m] = (0, l.useState)(""), [h, g] = (0, l.useState)(""), [_, v] = (0, l.useState)(""), y = (0, l.useCallback)(async () => {
		try {
			let e = await B("/api/portfolio/presets"), t = Array.isArray(e) ? e : e.presets || [];
			r(t), v((e) => e && t.some((t) => t.id === e && t.positions.length) ? e : t.find((e) => e.positions.length)?.id || ""), m("");
		} catch (e) {
			m(e instanceof Error ? e.message : "목표 비중을 불러오지 못했습니다.");
		}
	}, []);
	(0, l.useEffect)(() => {
		y();
	}, [y, e]), (0, l.useEffect)(() => {
		if (!_) {
			a(null);
			return;
		}
		let e = !1;
		return (async () => {
			try {
				let t = await B(`/api/portfolio/analytics?presetId=${encodeURIComponent(_)}`);
				e || a(t.analytics.targetWeights);
			} catch {
				e || a(null);
			}
		})(), () => {
			e = !0;
		};
	}, [_, e]);
	let b = async () => {
		u("create"), f(""), m("");
		try {
			let e = await V("/api/portfolio/presets/from-current", { name: o.trim() || "현재 포트폴리오 목표 비중" });
			s(""), await y(), t(), f(e.positions.length ? `${e.name} — ${e.positions.length}개 종목의 현재 비중을 목표로 저장했습니다.` : "보유 종목이 없어 빈 목표가 만들어졌습니다.");
		} catch (e) {
			m(e instanceof Error ? e.message : "목표를 만들지 못했습니다.");
		} finally {
			u("");
		}
	}, x = async (e) => {
		if (h !== e.id) {
			g(e.id);
			return;
		}
		u(e.id), m("");
		try {
			await W(`/api/portfolio/presets/${encodeURIComponent(e.id)}`, {}), g(""), _ === e.id && (v(""), a(null)), await y(), t(), f(`${e.name}을(를) 지웠습니다.`);
		} catch (e) {
			m(e instanceof Error ? e.message : "지우지 못했습니다.");
		} finally {
			u("");
		}
	};
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "portfolio-targets",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "portfolio-block__head",
						children: /* @__PURE__ */ (0, K.jsx)("h3", { children: "프리셋" })
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-note",
						children: "비중을 담은 포트폴리오 초안입니다. 현재 보유와 얼마나 벌어졌는지 보고, 백테스트를 돌리고, 여러 개를 나란히 비교하는 데 씁니다."
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-inline-form",
						children: [/* @__PURE__ */ (0, K.jsxs)("label", {
							className: "field",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "프리셋 이름" }), /* @__PURE__ */ (0, K.jsx)("input", {
								value: o,
								placeholder: "현재 포트폴리오 목표 비중",
								onChange: (e) => s(e.target.value)
							})]
						}), /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							onClick: () => void b(),
							disabled: !!c,
							children: c === "create" ? "만드는 중" : "현재 보유에서 만들기"
						})]
					}),
					n.length === 0 ? /* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-empty",
						children: "저장한 프리셋이 없습니다."
					}) : /* @__PURE__ */ (0, K.jsx)("ul", {
						className: "portfolio-preset-list",
						children: n.map((e) => /* @__PURE__ */ (0, K.jsxs)("li", {
							className: "portfolio-preset surface",
							children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.name }), /* @__PURE__ */ (0, K.jsxs)("small", { children: [
								e.positions.length,
								"종목 · 합계 ",
								Wc(e.weightTotal ?? 0),
								e.updatedAt ? ` · ${e.updatedAt.slice(0, 10)}` : ""
							] })] }), /* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn",
								type: "button",
								onClick: () => void x(e),
								disabled: c === e.id,
								children: c === e.id ? "지우는 중" : h === e.id ? "정말 지울까요?" : "지우기"
							})]
						}, e.id))
					})
				]
			}),
			n.some((e) => e.positions.length > 0) && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "portfolio-block__head",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "현재 보유와의 차이" }), /* @__PURE__ */ (0, K.jsxs)("label", {
							className: "field",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "기준 프리셋" }), /* @__PURE__ */ (0, K.jsx)("select", {
								value: _,
								onChange: (e) => v(e.target.value),
								children: n.filter((e) => e.positions.length > 0).map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
									value: e.id,
									children: e.name
								}, e.id))
							})]
						})]
					}),
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "portfolio-table-scroll",
						children: /* @__PURE__ */ (0, K.jsxs)("table", {
							className: "portfolio-mini-table",
							children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "종목"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "현재"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "목표"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "차이"
								}),
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "col",
									children: "조정 금액 (USD)"
								})
							] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: (i?.items ?? []).map((e) => /* @__PURE__ */ (0, K.jsxs)("tr", { children: [
								/* @__PURE__ */ (0, K.jsx)("th", {
									scope: "row",
									children: e.name || e.ticker
								}),
								/* @__PURE__ */ (0, K.jsx)("td", { children: Wc(e.currentWeight) }),
								/* @__PURE__ */ (0, K.jsx)("td", { children: Wc(e.targetWeight) }),
								/* @__PURE__ */ (0, K.jsx)("td", {
									"data-sign": Gc(e.diffWeight),
									children: Wc(e.diffWeight)
								}),
								/* @__PURE__ */ (0, K.jsx)("td", {
									"data-sign": Gc(e.diffAmountUsd),
									children: Uc(e.diffAmountUsd)
								})
							] }, e.id || e.ticker)) })]
						})
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-note",
						children: "차이가 양수면 이 프리셋보다 많이 들고 있다는 뜻입니다. 세금·수수료·최소 매매 단위는 반영하지 않았습니다."
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-block",
				children: [
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "portfolio-block__head",
						children: /* @__PURE__ */ (0, K.jsx)("h3", { children: "프리셋 비교" })
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "portfolio-note",
						children: "프리셋 2개 이상을 골라 같은 기간·같은 리밸런싱 조건으로 나란히 돌려 봅니다."
					}),
					/* @__PURE__ */ (0, K.jsx)(cl, { presets: n })
				]
			}),
			d && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-reader-status",
				role: "status",
				children: d
			}),
			p && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				role: "alert",
				children: p
			})
		]
	});
}
//#endregion
//#region src/app/PortfolioRoute.tsx
var ul = [
	{
		id: "holdings",
		label: "보유·평가"
	},
	{
		id: "targets",
		label: "프리셋"
	},
	{
		id: "backtest",
		label: "백테스트"
	}
];
function dl() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)([]), [i, a] = (0, l.useState)("holdings"), [o, s] = (0, l.useState)(!1), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)("");
	async function p() {
		let e = await B("/api/portfolio");
		t(e), r(e.positions || []);
	}
	(0, l.useEffect)(() => {
		p().catch((e) => f(e instanceof Error ? e.message : "Portfolio를 불러오지 못했습니다.")), Qe("portfolio", {
			surface: "portfolio",
			viewId: "portfolio",
			reportKind: "portfolio",
			reportId: "current"
		});
	}, []);
	async function m() {
		if (e) {
			s(!0), f(""), u("");
			try {
				let i = await V("/api/portfolio", {
					expectedRevision: e.revision,
					positions: n,
					cash: e.cash || []
				});
				t(i), r(i.positions || []), u(`revision ${i.revision}로 저장했습니다.`);
			} catch (e) {
				e instanceof F && e.status === 409 ? (await p(), f("다른 화면에서 Portfolio가 먼저 수정되어 최신본을 다시 불러왔습니다. 변경을 확인한 뒤 다시 저장하세요.")) : f(e instanceof Error ? e.message : "Portfolio 저장에 실패했습니다.");
			} finally {
				s(!1);
			}
		}
	}
	let h = e?.revision ?? 0;
	return /* @__PURE__ */ (0, K.jsxs)("main", {
		className: "portfolio-route",
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Portfolio",
				title: "보유 종목과 리서치 연결",
				description: "입력 부담을 줄이고, 보유 포지션에서 시작해 뉴스·브리핑·시장 내러티브를 함께 검토합니다."
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "segment portfolio-tabs",
				role: "group",
				"aria-label": "포트폴리오 보기",
				children: ul.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					"aria-pressed": i === e.id,
					onClick: () => a(e.id),
					children: e.label
				}, e.id))
			}),
			i === "holdings" && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "portfolio-route-grid",
				children: [/* @__PURE__ */ (0, K.jsxs)("section", {
					className: "cockpit-panel portfolio-holdings",
					"aria-labelledby": "portfolio-holdings-title",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "cockpit-panel__head",
							children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "HOLDINGS" }), /* @__PURE__ */ (0, K.jsx)("h2", {
								id: "portfolio-holdings-title",
								children: "현재 보유 종목"
							})] }), /* @__PURE__ */ (0, K.jsxs)("b", { children: ["버전 ", h] })]
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "portfolio-actions",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn",
								type: "button",
								onClick: () => r([...n, {
									ticker: "",
									quantity: "",
									averagePrice: ""
								}]),
								children: "종목 추가"
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn btn--primary",
								type: "button",
								disabled: o || !e,
								onClick: m,
								children: o ? "저장 중" : "Portfolio 저장"
							})]
						}),
						/* @__PURE__ */ (0, K.jsx)(zc, {
							positions: n,
							onChange: r
						}),
						c && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "react-reader-status",
							children: c
						}),
						d && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "react-dashboard-error",
							role: "alert",
							children: d
						}),
						/* @__PURE__ */ (0, K.jsx)(Jc, { revision: h })
					]
				}), /* @__PURE__ */ (0, K.jsxs)("aside", {
					className: "cockpit-panel portfolio-research",
					"aria-labelledby": "portfolio-research-title",
					children: [
						/* @__PURE__ */ (0, K.jsx)("div", {
							className: "cockpit-panel__head",
							children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "RESEARCH" }), /* @__PURE__ */ (0, K.jsx)("h2", {
								id: "portfolio-research-title",
								children: "Agent와 검토"
							})] })
						}),
						/* @__PURE__ */ (0, K.jsx)("p", { children: "현재 보유 종목을 기준으로 최근 뉴스, 브리핑, 시장 내러티브의 변화와 반대 근거를 함께 살펴봅니다." }),
						/* @__PURE__ */ (0, K.jsx)(Vc, { tickers: n.map((e) => e.ticker).filter(Boolean) }),
						/* @__PURE__ */ (0, K.jsx)("small", { children: "대화 내용은 보고서 근거로 사용되지 않습니다." })
					]
				})]
			}),
			i === "targets" && /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "cockpit-panel",
				"aria-labelledby": "portfolio-targets-title",
				children: [/* @__PURE__ */ (0, K.jsx)("div", {
					className: "cockpit-panel__head",
					children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "PRESETS" }), /* @__PURE__ */ (0, K.jsx)("h2", {
						id: "portfolio-targets-title",
						children: "프리셋"
					})] })
				}), /* @__PURE__ */ (0, K.jsx)(ll, {
					revision: h,
					onChanged: () => {
						p();
					}
				})]
			}),
			i === "backtest" && /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "cockpit-panel",
				"aria-labelledby": "portfolio-backtest-title",
				children: [/* @__PURE__ */ (0, K.jsx)("div", {
					className: "cockpit-panel__head",
					children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "BACKTEST" }), /* @__PURE__ */ (0, K.jsx)("h2", {
						id: "portfolio-backtest-title",
						children: "백테스트"
					})] })
				}), /* @__PURE__ */ (0, K.jsx)(Qc, { revision: h })]
			})
		]
	});
}
//#endregion
//#region src/app/agentWorkspace/ThreadList.tsx
var fl = {
	watchlist: "관심 종목",
	portfolio: "포트폴리오",
	briefing: "브리핑",
	company_analysis: "기업 분석",
	topic_report: "딥 리서치",
	market_memory: "시장 내러티브",
	change: "변화"
};
function pl(e) {
	if (!e || e.kind === "general") return "";
	let t = fl[e.kind] || e.kind, n = e.tickers && e.tickers[0] || e.id || "";
	return n ? `${n}` : t;
}
function ml(e) {
	if (!e) return "";
	let t = Date.parse(e);
	if (Number.isNaN(t)) return "";
	let n = Math.floor((Date.now() - t) / 6e4);
	if (n < 1) return "방금";
	if (n < 60) return `${n}분 전`;
	let r = Math.floor(n / 60);
	if (r < 24) return `${r}시간 전`;
	let i = Math.floor(r / 24);
	return i < 7 ? `${i}일 전` : new Date(t).toLocaleDateString();
}
function hl({ activeId: e, refreshKey: t, onSelect: n, onDeleted: r }) {
	let [i, a] = (0, l.useState)([]), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)(""), [p, m] = (0, l.useState)(""), h = (0, l.useCallback)(async () => {
		try {
			let e = await B("/api/agent/threads?limit=60");
			a(e.items || []), s("");
		} catch (e) {
			s(e instanceof Error ? e.message : "대화 목록을 불러오지 못했습니다.");
		}
	}, []);
	(0, l.useEffect)(() => {
		h();
	}, [h, t]);
	async function g(e) {
		if (window.confirm(`"${e.title}" 대화를 삭제할까요? 삭제 후 복구할 수 없습니다.`)) {
			u(e.id);
			try {
				await W(`/api/agent/threads/${encodeURIComponent(e.id)}`, { confirm: !0 }), r(e.id), await h();
			} catch (e) {
				s(e instanceof Error ? e.message : "삭제하지 못했습니다.");
			} finally {
				u("");
			}
		}
	}
	async function _(e) {
		u(e.id);
		try {
			await V(`/api/agent/threads/${encodeURIComponent(e.id)}/archive`, {}), await h();
		} catch (e) {
			s(e instanceof Error ? e.message : "보관하지 못했습니다.");
		} finally {
			u("");
		}
	}
	async function v(e) {
		let t = p.trim();
		if (f(""), !(!t || t === e.title)) {
			u(e.id);
			try {
				await V(`/api/agent/threads/${encodeURIComponent(e.id)}`, { title: t }), await h();
			} catch (e) {
				s(e instanceof Error ? e.message : "제목을 바꾸지 못했습니다.");
			} finally {
				u("");
			}
		}
	}
	let y = i.filter((e) => e.status !== "archived"), b = i.length - y.length;
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "agent-threads",
		"aria-label": "저장된 대화",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("p", {
				className: "agent-threads__summary",
				children: [/* @__PURE__ */ (0, K.jsx)("span", { children: y.length ? `대화 ${y.length}개` : "저장된 대화 없음" }), b > 0 && /* @__PURE__ */ (0, K.jsxs)("span", { children: [
					"보관 ",
					b,
					"개"
				] })]
			}),
			o && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "agent-threads__error",
				children: o
			}),
			!y.length && !o && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "agent-threads__empty",
				children: "질문을 보내면 대화가 여기에 저장됩니다."
			}),
			/* @__PURE__ */ (0, K.jsx)("ul", { children: y.map((t) => {
				let r = [
					pl(t.scope),
					t.messageCount ? `${t.messageCount}개` : "",
					ml(t.updatedAt)
				].filter(Boolean).join(" · ");
				return /* @__PURE__ */ (0, K.jsxs)("li", {
					"data-active": t.id === e ? "true" : void 0,
					children: [d === t.id ? /* @__PURE__ */ (0, K.jsx)("form", {
						className: "agent-threads__rename",
						onSubmit: (e) => {
							e.preventDefault(), v(t);
						},
						children: /* @__PURE__ */ (0, K.jsx)("input", {
							value: p,
							autoFocus: !0,
							"aria-label": "대화 제목",
							onChange: (e) => m(e.currentTarget.value),
							onBlur: () => void v(t)
						})
					}) : /* @__PURE__ */ (0, K.jsxs)("button", {
						type: "button",
						className: "agent-threads__open",
						"aria-current": t.id === e ? "true" : void 0,
						onClick: () => n(t.id),
						children: [/* @__PURE__ */ (0, K.jsx)("span", {
							className: "agent-threads__title",
							children: t.title
						}), /* @__PURE__ */ (0, K.jsx)("span", {
							className: "agent-threads__meta",
							children: r || "비어 있음"
						})]
					}), /* @__PURE__ */ (0, K.jsxs)("span", {
						className: "agent-threads__actions",
						children: [
							/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								className: "btn btn--icon btn--sm",
								disabled: c === t.id,
								"aria-label": `${t.title} 제목 바꾸기`,
								"data-tooltip": "제목",
								onClick: () => {
									f(t.id), m(t.title);
								},
								children: /* @__PURE__ */ (0, K.jsx)("svg", {
									viewBox: "0 0 16 16",
									width: "15",
									height: "15",
									"aria-hidden": "true",
									fill: "none",
									stroke: "currentColor",
									strokeWidth: "1.4",
									children: /* @__PURE__ */ (0, K.jsx)("path", {
										d: "M11 2.5l2.5 2.5-8 8H3v-2.5z",
										strokeLinejoin: "round"
									})
								})
							}),
							/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								className: "btn btn--icon btn--sm",
								disabled: c === t.id,
								"aria-label": `${t.title} 보관하기`,
								"data-tooltip": "보관",
								onClick: () => void _(t),
								children: /* @__PURE__ */ (0, K.jsx)("svg", {
									viewBox: "0 0 16 16",
									width: "15",
									height: "15",
									"aria-hidden": "true",
									fill: "none",
									stroke: "currentColor",
									strokeWidth: "1.4",
									children: /* @__PURE__ */ (0, K.jsx)("path", {
										d: "M2 4.5h12M3.5 4.5v8h9v-8M6.5 7.5h3",
										strokeLinecap: "round"
									})
								})
							}),
							/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								className: "btn btn--icon btn--sm",
								disabled: c === t.id,
								"aria-label": `${t.title} 삭제하기`,
								"data-tooltip": "삭제",
								onClick: () => void g(t),
								children: /* @__PURE__ */ (0, K.jsx)("svg", {
									viewBox: "0 0 16 16",
									width: "15",
									height: "15",
									"aria-hidden": "true",
									fill: "none",
									stroke: "currentColor",
									strokeWidth: "1.4",
									children: /* @__PURE__ */ (0, K.jsx)("path", {
										d: "M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5",
										strokeLinecap: "round",
										strokeLinejoin: "round"
									})
								})
							})
						]
					})]
				}, t.id);
			}) })
		]
	});
}
//#endregion
//#region src/app/agentWorkspace/useDockThreads.ts
var gl = "folio.agentThreads.migrated.v1";
function _l(e, t) {
	return {
		id: e.id || `restored-${t}`,
		role: e.role === "assistant" ? "assistant" : "user",
		text: String(e.content || ""),
		createdAt: e.createdAt
	};
}
function vl(e) {
	let [t, n] = (0, l.useState)(""), [r, i] = (0, l.useState)(null), [a, o] = (0, l.useState)(0), [s, c] = (0, l.useState)(null), u = (0, l.useRef)(!1), d = (0, l.useCallback)(() => o((e) => e + 1), []), f = (0, l.useCallback)(async (e = {}) => {
		let t = await V("/api/agent/threads", {
			title: e.title || "새 대화",
			scope: e.scope || { kind: "general" }
		});
		return n(t.id), c(t.scope || null), i(null), d(), t;
	}, [d]), p = (0, l.useCallback)(async (t) => {
		let r = await B(`/api/agent/threads/${encodeURIComponent(t)}`);
		n(r.id), c(r.scope || null), i(null);
		let a = r.messages || [];
		return a.length ? a.map(_l) : [{
			...e,
			createdAt: (/* @__PURE__ */ new Date()).toISOString()
		}];
	}, [e]), m = (0, l.useCallback)(async () => {
		if (u.current || (u.current = !0, window.localStorage.getItem(gl))) return;
		let e = xt().filter((e) => e.text && !mt(e));
		if (!e.length) {
			window.localStorage.setItem(gl, (/* @__PURE__ */ new Date()).toISOString());
			return;
		}
		try {
			let t = await V("/api/agent/threads", {
				title: "이전 대화",
				scope: { kind: "general" },
				importMessages: e.map((e) => ({
					role: e.role,
					content: e.text,
					createdAt: e.createdAt
				}))
			});
			if ((t.messageCount || 0) < e.length) {
				await W(`/api/agent/threads/${encodeURIComponent(t.id)}`, { confirm: !0 }).catch(() => {}), u.current = !1;
				return;
			}
			window.localStorage.setItem(gl, (/* @__PURE__ */ new Date()).toISOString()), Ct(), window.localStorage.removeItem(ft), d();
		} catch {
			u.current = !1;
		}
	}, [d]), h = (0, l.useCallback)(async (e) => {
		try {
			let t = (await B(`/api/agent/threads/${encodeURIComponent(e)}`)).messages || [];
			for (let e = t.length - 1; e >= 0; --e) if (t[e].role === "assistant") return String(t[e].content || "");
		} catch {}
		return "";
	}, []);
	return (0, l.useEffect)(() => {
		m();
	}, [m]), {
		threadId: t,
		setThreadId: n,
		scope: s,
		setScope: c,
		pending: r,
		setPending: i,
		refreshKey: a,
		bumpList: d,
		createThread: f,
		openThread: p,
		latestReply: h
	};
}
//#endregion
//#region src/app/ReactAgentDock.tsx
var yl = /* @__PURE__ */ new Set([
	"codex",
	"claude",
	"antigravity"
]), bl = {
	id: "welcome",
	role: "assistant",
	text: "현재 화면에 대해 물어보세요. 보고서 수정이나 발전 요청은 작업으로 전환해 처리합니다.",
	variant: "welcome",
	createdAt: (/* @__PURE__ */ new Date()).toISOString()
}, xl = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M19.503 0H4.496A4.496 4.496 0 000 4.496v15.007A4.496 4.496 0 004.496 24h15.007A4.496 4.496 0 0024 19.503V4.496A4.496 4.496 0 0019.503 0z\" fill=\"#fff\"></path><path d=\"M9.064 3.344a4.578 4.578 0 012.285-.312c1 .115 1.891.54 2.673 1.275.01.01.024.017.037.021a.09.09 0 00.043 0 4.55 4.55 0 013.046.275l.047.022.116.057a4.581 4.581 0 012.188 2.399c.209.51.313 1.041.315 1.595a4.24 4.24 0 01-.134 1.223.123.123 0 00.03.115c.594.607.988 1.33 1.183 2.17.289 1.425-.007 2.71-.887 3.854l-.136.166a4.548 4.548 0 01-2.201 1.388.123.123 0 00-.081.076c-.191.551-.383 1.023-.74 1.494-.9 1.187-2.222 1.846-3.711 1.838-1.187-.006-2.239-.44-3.157-1.302a.107.107 0 00-.105-.024c-.388.125-.78.143-1.204.138a4.441 4.441 0 01-1.945-.466 4.544 4.544 0 01-1.61-1.335c-.152-.202-.303-.392-.414-.617a5.81 5.81 0 01-.37-.961 4.582 4.582 0 01-.014-2.298.124.124 0 00.006-.056.085.085 0 00-.027-.048 4.467 4.467 0 01-1.034-1.651 3.896 3.896 0 01-.251-1.192 5.189 5.189 0 01.141-1.6c.337-1.112.982-1.985 1.933-2.618.212-.141.413-.251.601-.33.215-.089.43-.164.646-.227a.098.098 0 00.065-.066 4.51 4.51 0 01.829-1.615 4.535 4.535 0 011.837-1.388zm3.482 10.565a.637.637 0 000 1.272h3.636a.637.637 0 100-1.272h-3.636zM8.462 9.23a.637.637 0 00-1.106.631l1.272 2.224-1.266 2.136a.636.636 0 101.095.649l1.454-2.455a.636.636 0 00.005-.64L8.462 9.23z\" fill=\"url(#folio-react-codex-gradient)\"></path><defs><linearGradient gradientUnits=\"userSpaceOnUse\" id=\"folio-react-codex-gradient\" x1=\"12\" x2=\"12\" y1=\"3\" y2=\"21\"><stop stop-color=\"#B1A7FF\"></stop><stop offset=\".5\" stop-color=\"#7A9DFF\"></stop><stop offset=\"1\" stop-color=\"#3941FF\"></stop></linearGradient></defs></svg>", Sl = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M9.064 3.344a4.578 4.578 0 012.285-.312c1 .115 1.891.54 2.673 1.275.01.01.024.017.037.021a.09.09 0 00.043 0 4.55 4.55 0 013.046.275l.047.022.116.057a4.581 4.581 0 012.188 2.399c.209.51.313 1.041.315 1.595a4.24 4.24 0 01-.134 1.223.123.123 0 00.03.115c.594.607.988 1.33 1.183 2.17.289 1.425-.007 2.71-.887 3.854l-.136.166a4.548 4.548 0 01-2.201 1.388.123.123 0 00-.081.076c-.191.551-.383 1.023-.74 1.494-.9 1.187-2.222 1.846-3.711 1.838-1.187-.006-2.239-.44-3.157-1.302a.107.107 0 00-.105-.024c-.388.125-.78.143-1.204.138a4.441 4.441 0 01-1.945-.466 4.544 4.544 0 01-1.61-1.335c-.152-.202-.303-.392-.414-.617a5.81 5.81 0 01-.37-.961 4.582 4.582 0 01-.014-2.298.124.124 0 00.006-.056.085.085 0 00-.027-.048 4.467 4.467 0 01-1.034-1.651 3.896 3.896 0 01-.251-1.192 5.189 5.189 0 01.141-1.6c.337-1.112.982-1.985 1.933-2.618.212-.141.413-.251.601-.33.215-.089.43-.164.646-.227a.098.098 0 00.065-.066 4.51 4.51 0 01.829-1.615 4.535 4.535 0 011.837-1.388zm3.482 10.565a.637.637 0 000 1.272h3.636a.637.637 0 100-1.272h-3.636zM8.462 9.23a.637.637 0 00-1.106.631l1.272 2.224-1.266 2.136a.636.636 0 101.095.649l1.454-2.455a.636.636 0 00.005-.64L8.462 9.23z\" fill=\"currentColor\"/></svg>", Cl = "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z", wl = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${Cl}" fill="#D97757" fill-rule="nonzero"></path></svg>`, Tl = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${Cl}" fill="currentColor" fill-rule="nonzero"></path></svg>`, El = "M21.751 22.607c1.34 1.005 3.35.335 1.508-1.508C17.73 15.74 18.904 1 12.037 1 5.17 1 6.342 15.74.815 21.1c-2.01 2.009.167 2.511 1.507 1.506 5.192-3.517 4.857-9.714 9.715-9.714 4.857 0 4.522 6.197 9.714 9.715z", Dl = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${El}" fill="url(#folio-react-antigravity-gradient)"></path><defs><linearGradient id="folio-react-antigravity-gradient" x1="5" x2="19" y1="22" y2="2" gradientUnits="userSpaceOnUse"><stop stop-color="#3186FF"></stop><stop offset=".42" stop-color="#34A853"></stop><stop offset=".72" stop-color="#FBBC04"></stop><stop offset="1" stop-color="#EA4335"></stop></linearGradient></defs></svg>`, Ol = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${El}" fill="currentColor"></path></svg>`, kl = "<svg viewBox=\"0 0 24 24\" fill=\"currentColor\" aria-hidden=\"true\"><path d=\"M9 3c.4 3.9 3.1 6.6 7 7-3.9.4-6.6 3.1-7 7-.4-3.9-3.1-6.6-7-7 3.9-.4 6.6-3.1 7-7z\"/><path d=\"M17.8 13c.25 2.4 1.85 4 4.2 4.25-2.35.25-3.95 1.85-4.2 4.25-.25-2.4-1.85-4-4.2-4.25 2.35-.25 3.95-1.85 4.2-4.25z\" opacity=\".7\"/></svg>", Al = {
	codex: {
		label: "Codex",
		color: "#3941ff",
		logo: xl,
		monoLogo: Sl
	},
	claude: {
		label: "Claude",
		color: "#d97757",
		logo: wl,
		monoLogo: Tl
	},
	antigravity: {
		label: "Antigravity",
		color: "#3186ff",
		logo: Dl,
		monoLogo: Ol
	},
	default: {
		label: "Folio Agent",
		color: "#c79a45",
		logo: kl,
		monoLogo: kl
	}
};
function jl() {
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
function Ml(e) {
	return (e ? new Date(e) : /* @__PURE__ */ new Date()).toLocaleTimeString("ko-KR", {
		hour: "2-digit",
		minute: "2-digit"
	});
}
function Nl(e) {
	return e === "high" ? "높음" : e === "low" ? "낮음" : "중간";
}
function Pl(e) {
	return `${Math.max(1, Math.round((Date.now() - e) / 1e3))}초`;
}
var Fl = [
	"surface",
	"viewId",
	"reportKind",
	"reportId",
	"marketScope",
	"selectedText",
	"visibleSection",
	"portfolioLinked"
];
function Z(e) {
	if (!e) return {};
	let t = {};
	for (let n of Fl) Object.prototype.hasOwnProperty.call(e, n) && (t[n] = e[n]);
	return t;
}
function Q(e) {
	if (!e) return {};
	let t = Object.prototype.hasOwnProperty.call(e, "collectionId"), n = Object.prototype.hasOwnProperty.call(e, "collectionRevision");
	if (!t || !n) return {};
	let r = e.collectionId, i = e.collectionRevision;
	return r === null && i === null ? {
		collectionId: null,
		collectionRevision: null
	} : typeof r == "string" && r.trim().length > 0 && typeof i == "number" && Number.isInteger(i) && i >= 1 ? {
		collectionId: r,
		collectionRevision: i
	} : {};
}
function Il(e) {
	let t = { ...e };
	return delete t.collectionId, delete t.collectionRevision, t;
}
function Ll(e, t) {
	return e.ownerSurface === t ? e : {
		ownerSurface: t,
		patch: {}
	};
}
function Rl(e, t, n) {
	return {
		ownerSurface: t,
		patch: {
			...Ll(e, t).patch,
			...n,
			surface: String(n.surface || t)
		}
	};
}
function zl(e, t, n, r = {}) {
	let i = Ll(t, n);
	return {
		...Z(e),
		...Il(i.patch),
		...Il(r),
		...Q(e)
	};
}
function Bl(e) {
	return e?.provider && yl.has(e.provider) ? e.provider : e?.selectedAdapter || "";
}
function Vl(e, t = "") {
	let n = t && yl.has(t) ? t : Bl(e);
	return e?.adapters?.find((e) => e.id === n) || null;
}
function Hl(e, t = "") {
	return Al[t && yl.has(t) ? t : Bl(e)] || Al.default;
}
function Ul(e) {
	return e?.modelChoices || [];
}
function Wl(e) {
	let t = Ul(e);
	return t.length ? t.some((t) => t.value === e?.model) ? String(e?.model || "") : t[0].value : "";
}
function Gl({ surface: e, open: t, onOpen: n, onClose: r }) {
	let [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(null), [c, u] = (0, l.useState)([bl]), [d, f] = (0, l.useState)(!1), p = vl(bl), m = pl(p.scope || void 0), [h, g] = (0, l.useState)(""), [_, v] = (0, l.useState)(""), [y, b] = (0, l.useState)(""), [x, S] = (0, l.useState)("medium"), [C, w] = (0, l.useState)(!1), T = (0, l.useRef)(null), E = (0, l.useRef)(null), [D, O] = (0, l.useState)(!1), [k, A] = (0, l.useState)(""), j = (0, l.useRef)(null), M = (0, l.useRef)({
		ownerSurface: e,
		patch: {}
	}), N = (0, l.useRef)(/* @__PURE__ */ new Map());
	(0, l.useEffect)(() => () => {
		for (let e of N.current.values()) e.abort();
		N.current.clear();
	}, []), (0, l.useEffect)(() => {
		if (!C) return;
		let e = (e) => {
			T.current?.contains(e.target) || w(!1);
		}, t = (e) => {
			e.key === "Escape" && (w(!1), E.current?.focus());
		};
		return document.addEventListener("pointerdown", e), document.addEventListener("keydown", t, !0), () => {
			document.removeEventListener("pointerdown", e), document.removeEventListener("keydown", t, !0);
		};
	}, [C]);
	let P = (0, l.useCallback)((e, t = !1, n = "") => {
		let r = Vl(e, n);
		a(e), v((e) => {
			let n = Wl(r);
			return t && Ul(r).some((t) => t.value === e) ? e : n;
		});
	}, []), F = (0, l.useCallback)((e) => {
		b(e), v(Wl(Vl(i, e)));
	}, [i]), I = (0, l.useCallback)(async (e = !1) => {
		let t = await B(`/api/agent-bridge/settings${e ? "?refresh=true" : ""}`);
		return P(t, !0), t;
	}, [P]), L = (0, l.useCallback)(async (e) => {
		try {
			let t = e?.provider && yl.has(e.provider) ? e.provider : "", n = t ? `?adapter=${encodeURIComponent(t)}` : "";
			s(await B(`/api/agent-bridge/preflight${n}`));
		} catch (e) {
			s({
				ok: !1,
				checks: [{
					id: "preflight",
					label: "Agent Preflight",
					ok: !1,
					severity: "error",
					message: e instanceof Error ? e.message : "Agent 준비 상태를 확인하지 못했습니다."
				}]
			});
		}
	}, []);
	(0, l.useEffect)(() => {
		let e = !0;
		return B("/api/agent-bridge/settings").then((t) => {
			e && (P(t), L(t));
		}).catch((t) => {
			e && A(t instanceof Error ? t.message : "Agent 설정을 불러오지 못했습니다.");
		}), () => {
			e = !1;
		};
	}, [P, L]), (0, l.useEffect)(() => {
		j.current && (j.current.scrollTop = j.current.scrollHeight);
	}, [c, t]), (0, l.useEffect)(() => {
		M.current = Ll(M.current, e);
	}, [e]), (0, l.useEffect)(() => {
		let e = (e) => {
			let t = e.detail;
			t ? (P(t), L(t)) : I().then((e) => L(e)).catch((e) => A(e instanceof Error ? e.message : "Agent 설정을 불러오지 못했습니다."));
		};
		return window.addEventListener("folio:agent-settings-updated", e), () => window.removeEventListener("folio:agent-settings-updated", e);
	}, [
		P,
		I,
		L
	]);
	let R = Vl(i, y), z = Hl(i, y), H = Bl(i), U = !!y && y !== H, ee = Ul(R), te = [
		(R?.label || z.label || "").replace(/\s*(Code\s*)?CLI$/i, ""),
		ee.find((e) => e.value === _)?.label || _,
		Nl(x)
	].filter(Boolean).join(" · "), W = (0, l.useMemo)(() => ({ "--react-agent-accent": z.color }), [z.color]), G = (o?.checks || []).filter((e) => !e.ok), q = (0, l.useCallback)(async (t, n = {}) => {
		let r = t.trim();
		if (!r || D) return;
		M.current = Ll(M.current, e);
		let i = zl(window.FolioAgent?.currentContext, M.current, e, n), a = jl(), o = Date.now(), s = new Date(o).toISOString(), c = R?.label || z.label, l = _ || R?.model || "model";
		u((e) => [
			...e,
			{
				id: jl(),
				role: "user",
				text: r,
				createdAt: s
			},
			{
				id: a,
				role: "assistant",
				text: "",
				pending: !0,
				runState: "pending",
				runTitle: `${c} 세션 시작`,
				runMeta: `${l} · ${Nl(x)} · on-request`,
				createdAt: s
			}
		]), g(""), O(!0), A("");
		let d = null;
		try {
			let e = p.threadId || (await p.createThread({
				title: p.pending?.title || r.slice(0, 40),
				scope: p.pending?.scope
			})).id, t = await V(`/api/agent/threads/${encodeURIComponent(e)}/messages`, {
				message: r,
				operationId: jl(),
				context: i,
				options: {
					model: _,
					effort: x,
					adapter: y
				}
			});
			d = new AbortController(), st(N.current, a, d);
			let n = await ut(t.job, { signal: d.signal });
			ct(N.current, a, d);
			let s = {
				...n.result || {},
				reply: await p.latestReply(e)
			}, f = await je(s);
			p.bumpList(), u((e) => e.map((e) => e.id === a ? {
				...e,
				text: s.reply || n.message || "Agent가 응답을 반환하지 않았습니다.",
				notice: [s.notice, f.notice].filter(Boolean).join(" "),
				proposal: f.proposal,
				proposalStatus: f.proposalStatus,
				pending: !1,
				runState: "done",
				runTitle: `${c} 응답`,
				runMeta: `${l} · ${Nl(x)} · ${Pl(o)}`
			} : e));
		} catch (e) {
			if (d && ct(N.current, a, d), e instanceof at) {
				u((t) => t.map((t) => t.id === a ? {
					...t,
					text: e.message,
					pending: !1,
					runState: "still-running",
					runTitle: `${c} 계속 실행 중`,
					runMeta: `${l} · ${Nl(x)} · ${Pl(o)}`,
					jobId: e.job.id
				} : t));
				return;
			}
			let t = e instanceof Error ? e.message : "Agent 요청에 실패했습니다.";
			A(t), u((e) => e.map((e) => e.id === a ? {
				...e,
				text: t,
				pending: !1,
				runState: "error",
				runTitle: `${c} 오류`,
				runMeta: `${l} · ${Nl(x)}`
			} : e));
		} finally {
			O(!1);
		}
	}, [
		R?.label,
		R?.model,
		D,
		x,
		z.label,
		_,
		e,
		p.threadId,
		p.pending,
		p.createThread,
		p.latestReply,
		p.bumpList
	]);
	async function ne(e, t) {
		let n = new AbortController();
		st(N.current, e, n), u((t) => t.map((t) => t.id === e ? {
			...t,
			pending: !0,
			runState: "pending",
			runTitle: "Agent 상태 다시 확인 중"
		} : t));
		try {
			let r = await ut(await B(`/api/jobs/${encodeURIComponent(t)}`, { signal: n.signal }), { signal: n.signal }), i = {
				...r.result || {},
				reply: p.threadId ? await p.latestReply(p.threadId) : ""
			}, a = await je(i);
			p.bumpList(), u((t) => t.map((t) => t.id === e ? {
				...t,
				text: i.reply || r.message || "Agent가 응답을 반환하지 않았습니다.",
				notice: [i.notice, a.notice].filter(Boolean).join(" "),
				proposal: a.proposal,
				proposalStatus: a.proposalStatus,
				pending: !1,
				runState: "done",
				runTitle: "Agent 응답",
				jobId: void 0
			} : t));
		} catch (t) {
			t instanceof at ? u((n) => n.map((n) => n.id === e ? {
				...n,
				text: t.message,
				pending: !1,
				runState: "still-running",
				runTitle: "Agent 계속 실행 중",
				jobId: t.job.id
			} : n)) : t instanceof DOMException && t.name === "AbortError" || u((n) => n.map((n) => n.id === e ? {
				...n,
				text: t instanceof Error ? t.message : "Agent 상태 확인에 실패했습니다.",
				pending: !1,
				runState: "error",
				runTitle: "Agent 오류"
			} : n));
		} finally {
			ct(N.current, e, n);
		}
	}
	(0, l.useEffect)(() => {
		let t = (t) => {
			let { message: n, prompt: r, autoSubmit: i, ...a } = t.detail || {};
			M.current = Rl(M.current, e, a);
			let o = String(n || r || "");
			o && (i ? q(o, a) : g(o));
		};
		return window.addEventListener("folio:react-agent-request", t), () => window.removeEventListener("folio:react-agent-request", t);
	}, [q, e]), (0, l.useEffect)(() => {
		async function e(e) {
			let t = e.detail || {};
			t.scope && (p.setThreadId(""), p.setPending({
				title: t.title,
				scope: t.scope
			}), u([{
				...bl,
				createdAt: (/* @__PURE__ */ new Date()).toISOString()
			}]), f(!1), t.initialMessage && g(t.initialMessage));
		}
		return window.addEventListener("folio:open-agent-thread", e), () => window.removeEventListener("folio:open-agent-thread", e);
	}, [p]);
	async function re(e) {
		e.preventDefault(), await q(h);
	}
	function ie() {
		u([{
			...bl,
			createdAt: (/* @__PURE__ */ new Date()).toISOString()
		}]), g(""), A(""), p.setThreadId(""), p.setPending(null), f(!1);
	}
	async function se(e) {
		A("");
		try {
			u(await p.openThread(e)), f(!1);
		} catch (e) {
			A(e instanceof Error ? e.message : "대화를 불러오지 못했습니다.");
		}
	}
	function ce(e) {
		e === p.threadId && (p.setThreadId(""), p.setScope(null), u([{
			...bl,
			createdAt: (/* @__PURE__ */ new Date()).toISOString()
		}]));
	}
	async function le(e) {
		if (v(e), !(y || !R?.id || !e)) try {
			let t = Object.fromEntries((i?.adapters || []).map((e) => [e.id, e.model || ""]));
			t[R.id] = e;
			let n = await V("/api/agent-bridge/settings", {
				provider: R.id,
				models: t
			});
			P(n, !0), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: n }));
		} catch (e) {
			A(e instanceof Error ? e.message : "모델 설정 저장에 실패했습니다.");
		}
	}
	async function ue(e, t, n) {
		try {
			let r = await Ie(t, n);
			u((t) => t.map((t) => t.id === e ? {
				...t,
				proposalStatus: r.status
			} : t)), Le(r);
		} catch (e) {
			A(e instanceof Error ? e.message : "제안 처리에 실패했습니다.");
		}
	}
	return t ? /* @__PURE__ */ (0, K.jsxs)("aside", {
		className: "react-agent-dock",
		style: W,
		"aria-label": "AI Agent",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("header", {
				className: "react-agent-dock-header",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-agent-dock-title",
					children: [/* @__PURE__ */ (0, K.jsx)("span", {
						className: "react-agent-logo",
						"aria-hidden": "true",
						children: /* @__PURE__ */ (0, K.jsx)("span", {
							className: "react-agent-logo-mark",
							dangerouslySetInnerHTML: { __html: z.logo }
						})
					}), /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-kicker",
						children: "Agent"
					}), /* @__PURE__ */ (0, K.jsx)("h2", { children: R?.label || z.label })] })]
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-agent-header-actions",
					children: [
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "icon-btn",
							type: "button",
							"aria-label": "대화 목록",
							"aria-expanded": d,
							"data-tooltip": "대화 목록",
							"data-tooltip-pos": "bottom",
							onClick: () => f((e) => !e),
							children: /* @__PURE__ */ (0, K.jsx)("svg", {
								viewBox: "0 0 16 16",
								fill: "none",
								"aria-hidden": "true",
								width: "15",
								height: "15",
								children: /* @__PURE__ */ (0, K.jsx)("path", {
									d: "M3 4.5h10M3 8h10M3 11.5h6",
									stroke: "currentColor",
									strokeWidth: "1.6",
									strokeLinecap: "round"
								})
							})
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "icon-btn",
							type: "button",
							"aria-label": "새 대화",
							"data-tooltip": "새 대화",
							"data-tooltip-pos": "bottom",
							onClick: ie,
							children: /* @__PURE__ */ (0, K.jsx)("svg", {
								viewBox: "0 0 16 16",
								fill: "none",
								"aria-hidden": "true",
								width: "15",
								height: "15",
								children: /* @__PURE__ */ (0, K.jsx)("path", {
									d: "M8 3.5v9M3.5 8h9",
									stroke: "currentColor",
									strokeWidth: "1.7",
									strokeLinecap: "round"
								})
							})
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "icon-btn",
							type: "button",
							"aria-label": "AI Agent 닫기",
							"data-tooltip": "닫기",
							"data-tooltip-pos": "left",
							onClick: r,
							children: "×"
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-agent-dock-chrome",
				children: [
					d && /* @__PURE__ */ (0, K.jsx)(hl, {
						activeId: p.threadId,
						refreshKey: p.refreshKey,
						onSelect: (e) => void se(e),
						onDeleted: ce
					}),
					m && /* @__PURE__ */ (0, K.jsxs)("p", {
						className: "react-agent-scope",
						children: [/* @__PURE__ */ (0, K.jsx)("em", {
							className: "chip",
							children: m
						}), " 대화"]
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "react-agent-layer-note",
						children: "이 대화는 내 생각(가설)이며 보고서·Market Memory·근거 평가에 사용되지 않습니다."
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-agent-dock-body",
				ref: j,
				children: [
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "react-agent-watermark",
						"aria-hidden": "true",
						dangerouslySetInnerHTML: { __html: z.monoLogo }
					}),
					G.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "react-agent-preflight",
						role: "status",
						children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "Agent 준비 상태 확인 필요" }), G.slice(0, 3).map((e) => /* @__PURE__ */ (0, K.jsx)("p", { children: e.message }, e.id))]
					}),
					/* @__PURE__ */ (0, K.jsx)("div", {
						className: "react-agent-messages",
						children: c.map((e) => /* @__PURE__ */ (0, K.jsxs)("article", {
							className: `react-agent-message ${e.role}${e.pending ? " pending" : ""}`,
							children: [
								e.role === "assistant" && /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "react-agent-message-head",
									children: [
										/* @__PURE__ */ (0, K.jsx)("span", {
											className: "react-agent-mini-logo",
											"aria-hidden": "true",
											dangerouslySetInnerHTML: { __html: z.logo }
										}),
										/* @__PURE__ */ (0, K.jsx)("strong", { children: R?.label || z.label }),
										/* @__PURE__ */ (0, K.jsx)("time", { children: Ml(e.createdAt) })
									]
								}),
								e.runTitle && /* @__PURE__ */ (0, K.jsx)(oe, {
									state: e.runState === "still-running" ? "pending" : e.runState,
									title: e.runTitle,
									meta: e.runMeta
								}),
								e.runState === "still-running" && e.jobId && /* @__PURE__ */ (0, K.jsx)("div", {
									"data-qa": "agent-job-still-running",
									children: /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"data-qa": "agent-job-resume",
										onClick: () => void ne(e.id, e.jobId),
										children: "상태 다시 확인"
									})
								}),
								e.text && /* @__PURE__ */ (0, K.jsx)("div", {
									className: e.variant === "welcome" ? "react-agent-welcome-card" : "",
									children: /* @__PURE__ */ (0, K.jsx)(ae, { text: e.text })
								}),
								e.notice && /* @__PURE__ */ (0, K.jsx)("p", {
									className: "react-agent-notice",
									children: e.notice
								}),
								e.proposal && /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "agent-proposal",
									children: [
										/* @__PURE__ */ (0, K.jsxs)("div", {
											className: "agent-proposal-title",
											children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.proposal.artifactKind || "proposal" }), e.proposal.artifactId && /* @__PURE__ */ (0, K.jsx)("span", { children: e.proposal.artifactId })]
										}),
										e.proposalStatus === "pending" && e.proposal.summary && /* @__PURE__ */ (0, K.jsx)("p", {
											"data-qa": "proposal-summary",
											children: be(e.proposal.summary)
										}),
										e.proposalStatus === "pending" && e.proposal.diff && /* @__PURE__ */ (0, K.jsxs)("details", {
											className: "agent-proposal-diff",
											children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "diff 보기" }), /* @__PURE__ */ (0, K.jsx)("pre", {
												"data-qa": "proposal-diff",
												children: xe(e.proposal.diff)
											})]
										}),
										e.proposalStatus === "pending" ? /* @__PURE__ */ (0, K.jsxs)("div", {
											className: "agent-actions",
											children: [/* @__PURE__ */ (0, K.jsx)("button", {
												type: "button",
												"data-qa": "proposal-approve",
												onClick: () => ue(e.id, e.proposal.id, "approve"),
												children: "승인"
											}), /* @__PURE__ */ (0, K.jsx)("button", {
												type: "button",
												"data-qa": "proposal-reject",
												onClick: () => ue(e.id, e.proposal.id, "reject"),
												children: "거절"
											})]
										}) : /* @__PURE__ */ (0, K.jsxs)("p", {
											className: "agent-proposal-status",
											"data-qa": e.proposalStatus === "applied" ? "wb-happy-applied" : e.proposalStatus === "rejected" ? "wb-f1-terminal-rejected" : e.proposalStatus === "stale" ? "wb-f1-terminal-stale" : "proposal-terminal",
											children: ["상태: ", e.proposalStatus]
										})
									]
								})
							]
						}, e.id))
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsxs)("form", {
				className: "react-agent-form",
				onSubmit: re,
				children: [
					/* @__PURE__ */ (0, K.jsx)("textarea", {
						"data-qa": "agent-input",
						value: h,
						onChange: (e) => g(e.currentTarget.value),
						onKeyDown: (e) => {
							e.key === "Enter" && !e.shiftKey && (e.preventDefault(), e.currentTarget.form?.requestSubmit());
						},
						rows: 2,
						placeholder: "현재 화면에 대해 물어보세요"
					}),
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "react-agent-form-toolbar",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "react-agent-tools",
							ref: T,
							children: [/* @__PURE__ */ (0, K.jsxs)("button", {
								type: "button",
								className: "react-agent-run-trigger",
								ref: E,
								"aria-haspopup": "dialog",
								"aria-expanded": C,
								"aria-label": `실행 설정: ${te}`,
								title: te,
								onClick: () => w((e) => !e),
								children: [/* @__PURE__ */ (0, K.jsxs)("svg", {
									viewBox: "0 0 16 16",
									fill: "none",
									"aria-hidden": "true",
									width: "14",
									height: "14",
									children: [
										/* @__PURE__ */ (0, K.jsx)("path", {
											d: "M2.5 5h11M2.5 11h11",
											stroke: "currentColor",
											strokeWidth: "1.5",
											strokeLinecap: "round"
										}),
										/* @__PURE__ */ (0, K.jsx)("circle", {
											cx: "6",
											cy: "5",
											r: "1.9",
											fill: "currentColor"
										}),
										/* @__PURE__ */ (0, K.jsx)("circle", {
											cx: "10.5",
											cy: "11",
											r: "1.9",
											fill: "currentColor"
										})
									]
								}), /* @__PURE__ */ (0, K.jsx)("span", { children: te })]
							}), C && /* @__PURE__ */ (0, K.jsxs)("div", {
								className: "react-agent-run-menu",
								role: "dialog",
								"aria-label": "실행 설정",
								children: [
									/* @__PURE__ */ (0, K.jsxs)("label", { children: [
										/* @__PURE__ */ (0, K.jsx)("span", { children: "이 대화의 CLI" }),
										/* @__PURE__ */ (0, K.jsx)("select", {
											value: y || H,
											onChange: (e) => F(e.currentTarget.value === H ? "" : e.currentTarget.value),
											children: (i?.adapters || []).map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
												value: e.id,
												disabled: e.bridgeSupported === !1,
												children: e.label || e.id
											}, e.id))
										}),
										/* @__PURE__ */ (0, K.jsx)("small", { children: "이 대화에만 적용됩니다. 전역 기본은 상단바와 설정에서 바꿉니다." })
									] }),
									/* @__PURE__ */ (0, K.jsxs)("label", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "모델 버전" }), /* @__PURE__ */ (0, K.jsx)("select", {
										value: _,
										onChange: (e) => le(e.currentTarget.value),
										children: ee.length ? ee.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
											value: e.value,
											children: e.label
										}, e.value)) : /* @__PURE__ */ (0, K.jsx)("option", {
											value: "",
											children: "기본 버전"
										})
									})] }),
									/* @__PURE__ */ (0, K.jsxs)("label", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "노력 단계" }), /* @__PURE__ */ (0, K.jsxs)("select", {
										value: x,
										onChange: (e) => S(e.currentTarget.value),
										children: [
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "low",
												children: "노력 낮음"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "medium",
												children: "노력 중간"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "high",
												children: "노력 높음"
											}),
											/* @__PURE__ */ (0, K.jsx)("option", {
												value: "max",
												children: "노력 최대"
											})
										]
									})] })
								]
							})]
						}), /* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary btn--sm",
							type: "submit",
							"data-qa": "agent-submit",
							disabled: D || !h.trim(),
							children: D ? "작업 중" : "보내기"
						})]
					}),
					U && /* @__PURE__ */ (0, K.jsxs)("p", {
						className: "react-agent-scope-note",
						children: [
							"이 대화만 ",
							R?.label || y,
							"로 돕니다. 전역 기본은 그대로입니다."
						]
					}),
					k && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "react-agent-error",
						children: k
					})
				]
			})
		]
	}) : /* @__PURE__ */ (0, K.jsx)("aside", {
		className: "react-agent-dock is-closed",
		style: W,
		"aria-label": "AI Agent 닫힘",
		children: /* @__PURE__ */ (0, K.jsxs)("button", {
			type: "button",
			onClick: n,
			"aria-label": "AI Agent 열기",
			"data-tooltip": "AI Agent 열기",
			"data-tooltip-pos": "left",
			children: [/* @__PURE__ */ (0, K.jsx)("span", {
				className: "react-agent-closed-dot",
				"aria-hidden": "true"
			}), /* @__PURE__ */ (0, K.jsx)("span", { children: "AI" })]
		})
	});
}
//#endregion
//#region src/app/RssRoute.tsx
var Kl = "자료 위치를 옮겼습니다. 서버를 재시작하기 전까지는 RSS 수집과 보관 기간 정리를 실행하지 않습니다 — 지금 수집하면 새 자료가 옛 폴더와 새 폴더로 갈립니다.", ql = {
	start: "",
	end: "",
	source: "",
	market: "",
	language: ""
}, Jl = 20, Yl = [
	{
		value: "",
		label: "전체 시장"
	},
	{
		value: "US",
		label: "미국"
	},
	{
		value: "KR",
		label: "한국"
	},
	{
		value: "EUROPE",
		label: "유럽"
	},
	{
		value: "JP",
		label: "일본"
	},
	{
		value: "GLOBAL",
		label: "글로벌"
	}
], Xl = {
	en: "영어",
	de: "독일어",
	fr: "프랑스어",
	nl: "네덜란드어",
	it: "이탈리아어",
	es: "스페인어",
	ja: "일본어",
	ko: "한국어"
};
function Zl(e) {
	return new Promise((t) => window.setTimeout(t, e));
}
function Ql(e) {
	let t = e.timestamp || e.date || "";
	if (!t) return "시간 정보 없음";
	let n = new Date(t);
	return Number.isNaN(n.getTime()) ? t : n.toLocaleString("ko-KR");
}
function $l(e) {
	let t = [
		e.start ? `${e.start} 이후` : "",
		e.end ? `${e.end} 이전` : "",
		e.source ? e.source : "",
		e.market ? Yl.find((t) => t.value === e.market)?.label || e.market : "",
		e.language ? Xl[e.language] || e.language : ""
	].filter(Boolean);
	return t.length ? t.join(" · ") : "전체 RSS 피드";
}
function eu(e, t) {
	let n = new URLSearchParams({
		offset: String((Math.max(1, e) - 1) * Jl),
		limit: String(Jl)
	});
	return t.start && n.set("start", t.start), t.end && n.set("end", t.end), t.source && n.set("source", t.source), t.market && n.set("market", t.market), t.language && n.set("language", t.language), n;
}
function tu(e) {
	let t = e.markets, n = Array.isArray(t) ? t : typeof t == "string" ? t.split(",") : String(e.market || "").split(","), r = /* @__PURE__ */ new Set();
	return n.map((e) => String(e || "").trim()).filter(Boolean).filter((e) => !r.has(e) && (r.add(e), !0));
}
async function nu(e) {
	let t = e;
	for (; I(t.status);) await Zl(1e3), t = await B(`/api/jobs/${encodeURIComponent(t.id)}`);
	if (t.status !== "done") throw Error(t.message || t.error || "RSS 수집 작업에 실패했습니다.");
	return t;
}
function ru(e, t) {
	return e.url || `${e.title || "rss"}-${e.timestamp || e.date || t}`;
}
function iu(e) {
	return {
		title: e.title || e.headline || e.path || "검색 결과",
		url: e.url || e.sourceUrl || e.link || "",
		description: e.summary || e.snippet || e.text || e.content || "",
		media: e.media || e.source || e.collector || "",
		source: e.source || e.media || e.collector || "",
		markets: tu({
			markets: e.markets,
			market: String(e.market || "")
		}),
		market: String(e.market || ""),
		timestamp: e.timestamp || e.date || e.publishedAt || e.published || "",
		date: e.date || e.publishedAt || e.published || e.timestamp || ""
	};
}
function au() {
	let { isSelected: e } = vn(), t = fn("rss"), [n, r] = (0, l.useState)(null), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(1), [c, u] = (0, l.useState)(ql), [d, f] = (0, l.useState)(ql), [p, m] = (0, l.useState)(""), [h, g] = (0, l.useState)(!1), [_, v] = (0, l.useState)(!1), [y, b] = (0, l.useState)(!1), [x, S] = (0, l.useState)(""), [C, w] = (0, l.useState)(""), [T, E] = (0, l.useState)(!1), D = i?.items || [], O = i?.total ?? D.length, k = Math.max(1, Math.ceil(O / Jl)), A = (0, l.useMemo)(() => i?.sources || [], [i?.sources]), j = (0, l.useMemo)(() => i?.languages || [], [i?.languages]), M = (0, l.useCallback)(async (e = o, t = c) => {
		g(!0), S("");
		try {
			let n = await B(`/api/rss/items?${eu(e, t).toString()}`);
			a(n), E(!1), s(e), u(t), f(t), Qe("rss", {
				surface: "rss",
				viewId: "rssfeed",
				reportKind: "",
				reportId: ""
			});
		} catch (e) {
			S(e instanceof Error ? e.message : "RSS 피드를 불러오지 못했습니다.");
		} finally {
			g(!1);
		}
	}, [c, o]), N = (0, l.useCallback)(async () => {
		try {
			let e = await B("/api/dashboard"), t = e.index?.newsCount ?? e.index?.count;
			Number.isFinite(Number(t)) && r(Number(t));
		} catch {}
	}, []);
	(0, l.useEffect)(() => {
		M(1, c), N();
	}, []);
	let P = (0, l.useRef)(!0);
	(0, l.useEffect)(() => {
		if (P.current) {
			P.current = !1;
			return;
		}
		M(1, c), N();
	}, [t]);
	async function F(e) {
		let t = {
			...d,
			...e
		};
		if (f(t), t.start && t.end && t.start > t.end) {
			S("시작 시간은 종료 시간보다 앞서야 합니다.");
			return;
		}
		S(""), w(""), await M(1, t);
	}
	async function I() {
		w(""), m(""), f(ql), await M(1, ql);
	}
	async function L(e) {
		e?.preventDefault();
		let t = p.trim();
		if (!t) {
			S("검색어를 입력해 주세요.");
			return;
		}
		b(!0), S(""), w("");
		try {
			let e = await B(`/api/search?${new URLSearchParams({
				query: t,
				scope: "news",
				limit: "50"
			}).toString()}`), n = Array.isArray(e) ? e : e.items || [];
			a({
				items: n.map(iu),
				total: n.length,
				offset: 0,
				limit: n.length,
				has_more: !1,
				sources: A
			}), E(!0), s(1), w(`뉴스 검색 결과 ${n.length}개`), Qe("rss", {
				surface: "rss",
				viewId: "rssfeed",
				reportKind: "news_search",
				reportId: t
			});
		} catch (e) {
			S(e instanceof Error ? e.message : "뉴스 검색에 실패했습니다.");
		} finally {
			b(!1);
		}
	}
	async function R() {
		v(!0), S(""), w("RSS 수집 작업을 시작했습니다.");
		try {
			let e = await nu(await V("/api/rssarchive/import", {}));
			if (e.result?.skipped === "workspace_moved") {
				w(Kl);
				return;
			}
			let t = Number.isFinite(Number(e.result?.added)) ? ` 신규 ${e.result?.added}개` : "";
			w(`RSS 수집 완료.${t}`), await M(1, c), await N();
		} catch (e) {
			S(e instanceof Error ? e.message : "RSS 수집에 실패했습니다."), w("");
		} finally {
			v(!1);
		}
	}
	let z = Math.min(Math.max(o, 1), k), H = Math.max(1, z - 2), U = Math.min(k, z + 2), ee = O > 0 ? T ? `${O}개` : `${O}개 · ${z}/${k}` : "0개";
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-rss-route",
		"data-rss-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "RSS Feed",
				title: "RSS 피드",
				description: "시장·국가·언어·기간·소스로 좁히거나 본문까지 검색합니다. 시간은 UTC+9 기준입니다.",
				actions: /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-rss-hero-actions",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("span", {
							className: "react-rss-stat-pill",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "LOADED" }), ee]
						}),
						/* @__PURE__ */ (0, K.jsxs)("span", {
							className: "react-rss-stat-pill",
							children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "INDEXED" }), n === null ? "…" : `${n}개 문서`]
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--primary",
							type: "button",
							onClick: R,
							disabled: _,
							children: _ ? "수집 중" : "RSS 수집/가져오기"
						})
					]
				})
			}),
			/* @__PURE__ */ (0, K.jsxs)("section", {
				className: "find-bar find-bar--stacked",
				"aria-label": "RSS 필터와 검색",
				children: [/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "find-bar__row",
					children: [/* @__PURE__ */ (0, K.jsx)("input", {
						type: "search",
						"aria-label": "본문 검색어",
						value: p,
						placeholder: "기업, 티커, 섹터 또는 이슈",
						onChange: (e) => m(e.currentTarget.value),
						onKeyDown: (e) => {
							e.key === "Enter" && (e.preventDefault(), L());
						},
						className: "find-bar__search"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => L(),
						disabled: y,
						children: y ? "검색 중" : "본문 검색"
					})]
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "find-bar__more",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("label", {
							className: "find-bar__field",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시장" }), /* @__PURE__ */ (0, K.jsx)("select", {
								value: d.market,
								onChange: (e) => void F({ market: e.currentTarget.value }),
								children: Yl.filter((t) => !t.value || e(t.value)).map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
									value: e.value,
									children: e.label
								}, e.value || "all-market"))
							})]
						}),
						/* @__PURE__ */ (0, K.jsxs)("label", {
							className: "find-bar__field",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "소스" }), /* @__PURE__ */ (0, K.jsxs)("select", {
								value: d.source,
								onChange: (e) => void F({ source: e.currentTarget.value }),
								children: [/* @__PURE__ */ (0, K.jsx)("option", {
									value: "",
									children: "전체 소스"
								}), A.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
									value: e,
									children: e
								}, e))]
							})]
						}),
						/* @__PURE__ */ (0, K.jsxs)("label", {
							className: "find-bar__field",
							children: [
								/* @__PURE__ */ (0, K.jsx)("span", { children: "기간" }),
								/* @__PURE__ */ (0, K.jsx)("input", {
									type: "datetime-local",
									"aria-label": "시작",
									value: d.start,
									onChange: (e) => void F({ start: e.currentTarget.value })
								}),
								/* @__PURE__ */ (0, K.jsx)("input", {
									type: "datetime-local",
									"aria-label": "종료",
									value: d.end,
									onChange: (e) => void F({ end: e.currentTarget.value })
								})
							]
						}),
						/* @__PURE__ */ (0, K.jsxs)("details", {
							className: "find-bar__detail",
							children: [/* @__PURE__ */ (0, K.jsx)("summary", { children: "상세" }), /* @__PURE__ */ (0, K.jsxs)("label", {
								className: "find-bar__field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "언어" }), /* @__PURE__ */ (0, K.jsxs)("select", {
									value: d.language,
									onChange: (e) => void F({ language: e.currentTarget.value }),
									children: [/* @__PURE__ */ (0, K.jsx)("option", {
										value: "",
										children: "전체 언어"
									}), j.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
										value: e,
										children: Xl[e] || e
									}, e))]
								})]
							})]
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--text find-bar__reset",
							type: "button",
							onClick: I,
							disabled: h,
							children: "초기화"
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "react-rss-summary",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: T ? `"${p.trim()}" 검색 결과` : $l(c) }), /* @__PURE__ */ (0, K.jsx)("span", { children: ee })]
			}),
			x && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: x
			}),
			C && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				children: C
			}),
			/* @__PURE__ */ (0, K.jsx)("section", {
				className: "react-rss-feed",
				"aria-label": "RSS feed items",
				children: D.length ? D.map((e, t) => {
					let n = ru(e, t), r = String(e.description || "").trim(), i = tu(e);
					return /* @__PURE__ */ (0, K.jsxs)("article", {
						className: "react-rss-card",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "react-rss-card-main",
							children: [
								/* @__PURE__ */ (0, K.jsx)("h2", { children: e.url ? /* @__PURE__ */ (0, K.jsx)("a", {
									href: e.url,
									target: "_blank",
									rel: "noopener noreferrer",
									children: e.title || "제목 없음"
								}) : e.title || "제목 없음" }),
								/* @__PURE__ */ (0, K.jsxs)("div", {
									className: "react-rss-card-meta",
									children: [
										(e.media || e.source) && /* @__PURE__ */ (0, K.jsx)("span", {
											className: "pill",
											children: e.media || e.source
										}),
										i.length ? /* @__PURE__ */ (0, K.jsx)("span", {
											className: "pill",
											children: i.join(" · ")
										}) : null,
										/* @__PURE__ */ (0, K.jsx)("span", { children: Ql(e) })
									]
								}),
								r && /* @__PURE__ */ (0, K.jsx)("p", { children: r })
							]
						}), /* @__PURE__ */ (0, K.jsx)("div", {
							className: "react-rss-card-actions",
							children: e.url && /* @__PURE__ */ (0, K.jsx)("a", {
								className: "btn",
								href: e.url,
								target: "_blank",
								rel: "noopener noreferrer",
								children: "기사 열기"
							})
						})]
					}, n);
				}) : /* @__PURE__ */ (0, K.jsxs)("article", {
					className: "react-dashboard-panel",
					children: [/* @__PURE__ */ (0, K.jsx)("h2", { children: h ? "불러오는 중" : "표시할 RSS 피드가 없습니다." }), /* @__PURE__ */ (0, K.jsx)("p", { children: h ? "수집된 항목을 확인하고 있습니다." : "RSS 수집을 실행하거나 필터를 초기화해 보세요." })]
				})
			}),
			!T && k > 1 && /* @__PURE__ */ (0, K.jsxs)("nav", {
				className: "react-rss-pagination",
				"aria-label": "RSS pagination",
				children: [
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						disabled: z === 1 || h,
						onClick: () => M(z - 1, c),
						children: "이전"
					}),
					H > 1 && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => M(1, c),
						children: "1"
					}), H > 2 && /* @__PURE__ */ (0, K.jsx)("span", { children: "..." })] }),
					Array.from({ length: U - H + 1 }, (e, t) => H + t).map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						"aria-current": e === z ? "page" : void 0,
						disabled: h,
						onClick: () => M(e, c),
						children: e
					}, e)),
					U < k && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [U < k - 1 && /* @__PURE__ */ (0, K.jsx)("span", { children: "..." }), /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => M(k, c),
						children: k
					})] }),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						disabled: z === k || h,
						onClick: () => M(z + 1, c),
						children: "다음"
					})
				]
			})
		]
	});
}
//#endregion
//#region src/app/aiConnectionStatus.ts
function ou(e) {
	return !!(e.authenticated || e.available);
}
function su(e) {
	return e.bridgeSupported === !1 ? "지원 안 됨" : e.installed ? ou(e) ? "사용 가능" : "로그인 필요" : "미설치";
}
function cu(e) {
	return e.bridgeSupported === !1 ? "warn" : ou(e) ? "ready" : e.installed ? "warn" : "";
}
function lu(e) {
	return e.error ? e.error : e.version ? e.version : e.installed ? e.model || "모델 미설정" : "설치되어 있지 않습니다.";
}
function uu(e) {
	return e.bridgeSupported === !1 ? {
		install: "none",
		login: !1,
		docs: !!e.docsUrl
	} : e.installed ? {
		install: "none",
		login: !ou(e),
		docs: !!e.docsUrl
	} : {
		install: e.installSupported ? "button" : e.docsUrl ? "docs" : "none",
		login: !1,
		docs: !1
	};
}
function du(e) {
	if (!e) return "";
	let t = new Date(e);
	if (Number.isNaN(t.getTime())) return "";
	let n = (e) => String(e).padStart(2, "0");
	return `${n(t.getMonth() + 1)}.${n(t.getDate())} ${n(t.getHours())}:${n(t.getMinutes())}`;
}
//#endregion
//#region src/app/AgentCliSetup.tsx
var fu = 62e4;
function pu({ adapters: e, onSettings: t, disabled: n = !1 }) {
	let [r, i] = (0, l.useState)(""), [a, o] = (0, l.useState)(""), [s, c] = (0, l.useState)(""), u = (0, l.useRef)(null);
	function d(e) {
		t(e), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: e }));
	}
	async function f() {
		i("refresh"), o("");
		try {
			d(await B("/api/agent-bridge/settings?refresh=true"));
		} catch (e) {
			o(e instanceof Error ? e.message : "상태를 확인하지 못했습니다.");
		} finally {
			i("");
		}
	}
	async function p(e) {
		i(`install:${e.id}`), o(""), c("공식 설치 스크립트를 실행하고 있습니다.");
		let t = new AbortController();
		u.current?.abort(), u.current = t;
		try {
			await ut(await V(`/api/agent-bridge/install/${encodeURIComponent(e.id)}`, {}), {
				signal: t.signal,
				timeoutMs: fu,
				onUpdate: (e) => c(e.message || "")
			}), d(await B("/api/agent-bridge/settings?refresh=true")), o(`${e.label || e.id} 설치가 끝났습니다. 이어서 로그인하세요.`);
		} catch (e) {
			o(e instanceof Error ? e.message : "설치하지 못했습니다.");
		} finally {
			c(""), i("");
		}
	}
	async function m(e) {
		i(`login:${e.id}`), o("");
		try {
			await V(`/api/agent-bridge/login/${encodeURIComponent(e.id)}`, {}), o("로그인 창을 열었습니다. 창에서 로그인을 마친 뒤 상태 새로고침을 누르세요.");
		} catch (e) {
			o(e instanceof Error ? e.message : "로그인 창을 열지 못했습니다.");
		} finally {
			i("");
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "cli-setup",
		children: [
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cli-provider-list",
				"aria-live": "polite",
				children: [e.length === 0 && /* @__PURE__ */ (0, K.jsx)("p", {
					className: "cli-setup-note",
					children: "CLI 상태를 확인하는 중입니다."
				}), e.map((e) => {
					let t = uu(e), i = r === `install:${e.id}`;
					return /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "cli-provider-row",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "cli-provider-main",
							children: [/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "cli-provider-head",
								children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.label || e.id }), /* @__PURE__ */ (0, K.jsx)("span", {
									className: `cli-chip status-chip ${cu(e)}`,
									children: su(e)
								})]
							}), /* @__PURE__ */ (0, K.jsx)("div", {
								className: "cli-provider-meta",
								children: i ? s || "설치 중" : lu(e)
							})]
						}), /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "cli-provider-actions",
							children: [
								t.install === "button" && /* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									disabled: n || !!r,
									onClick: () => void p(e),
									children: i ? "설치 중" : "설치"
								}),
								t.install === "docs" && /* @__PURE__ */ (0, K.jsx)("a", {
									className: "btn",
									href: e.docsUrl,
									target: "_blank",
									rel: "noreferrer",
									children: "설치 방법"
								}),
								t.login && /* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									disabled: n || !!r,
									onClick: () => void m(e),
									children: r === `login:${e.id}` ? "여는 중" : "로그인"
								}),
								t.docs && /* @__PURE__ */ (0, K.jsx)("a", {
									className: "btn",
									href: e.docsUrl,
									target: "_blank",
									rel: "noreferrer",
									children: "문서"
								})
							]
						})]
					}, e.id);
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "cli-setup-foot",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					disabled: n || !!r,
					onClick: () => void f(),
					children: r === "refresh" ? "확인 중" : "상태 새로고침"
				}), /* @__PURE__ */ (0, K.jsxs)("p", {
					className: "cli-setup-note",
					children: [
						"설치는 공식 스크립트를 실행하며 Windows에서만 됩니다. 로그인은 ",
						/* @__PURE__ */ (0, K.jsx)("b", { children: "별도 콘솔 창" }),
						"에서 진행되고, 마친 뒤 상태 새로고침을 눌러야 반영됩니다. 새로고침은 CLI마다 모델 목록까지 다시 물어 시간이 걸립니다."
					]
				})]
			}),
			a && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "cli-setup-note cli-setup-note--result",
				role: "status",
				children: a
			})
		]
	});
}
//#endregion
//#region src/app/homePreference.ts
var mu = "folio.homePreference.v1", hu = "folio.agentCharacter.v1", gu = "folio.motionPreference.v1", _u = "folio:ui-preferences-updated", vu = {
	home: {
		mode: "home",
		choiceSeen: !0
	},
	character: {
		preset: "classic",
		name: ""
	},
	motion: "system"
};
function yu(e) {
	if (typeof window > "u") return "";
	try {
		return window.localStorage.getItem(e) || "";
	} catch {
		return "";
	}
}
function bu(e) {
	if (!e) return {};
	try {
		let t = JSON.parse(e);
		return t && typeof t == "object" && !Array.isArray(t) ? t : {};
	} catch {
		return {};
	}
}
function xu() {
	let e = bu(yu(mu)), t = bu(yu(hu)), n = yu(gu);
	return {
		home: {
			mode: e.mode === "home" ? "home" : "office",
			choiceSeen: e.choiceSeen === !0
		},
		character: {
			preset: t.preset === "student" ? "student" : "classic",
			name: typeof t.name == "string" ? t.name.trim().slice(0, 30) : ""
		},
		motion: n === "reduced" ? "reduced" : "system"
	};
}
function Su(e, t) {
	if (!(typeof window > "u")) try {
		window.localStorage.setItem(e, typeof t == "string" ? t : JSON.stringify(t));
	} catch {}
}
function Cu(e) {
	typeof window > "u" || window.dispatchEvent(new CustomEvent(_u, { detail: e }));
}
function wu(e) {
	return Su(mu, e.home), Su(hu, e.character), Su(gu, e.motion), Cu(e), e;
}
function Tu() {
	if (typeof window < "u") try {
		window.localStorage.removeItem(mu), window.localStorage.removeItem(hu), window.localStorage.removeItem(gu);
	} catch {}
	let e = structuredClone(vu);
	return Cu(e), e;
}
function Eu(e = xu()) {
	return "home";
}
function Du() {
	let [e, t] = (0, l.useState)(() => xu());
	(0, l.useEffect)(() => {
		let e = (e) => {
			let n = e.detail;
			t(n || xu());
		}, n = () => t(xu());
		return window.addEventListener(_u, e), window.addEventListener("storage", n), () => {
			window.removeEventListener(_u, e), window.removeEventListener("storage", n);
		};
	}, []);
	function n(e) {
		t(e), wu(e);
	}
	return {
		preferences: e,
		setHome(t, r = !0) {
			n({
				...e,
				home: {
					mode: t,
					choiceSeen: r
				}
			});
		},
		setCharacter(t, r = e.character.name) {
			n({
				...e,
				character: {
					preset: t,
					name: r.trim().slice(0, 30)
				}
			});
		},
		setMotion(t) {
			n({
				...e,
				motion: t
			});
		},
		reset() {
			let e = Tu();
			t(e);
		}
	};
}
//#endregion
//#region src/app/themePreference.ts
function Ou(e) {
	return e === "light" || e === "dark" || e === "system";
}
function ku(e) {
	return e === "light" || e === "dark";
}
function Au() {
	return {
		preference: Ou(window.FolioTheme?.preference) ? window.FolioTheme.preference : "system",
		resolved: ku(window.FolioTheme?.resolved) ? window.FolioTheme.resolved : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
	};
}
function ju() {
	let [e, t] = (0, l.useState)(Au);
	return (0, l.useEffect)(() => {
		let e = (e) => {
			let n = e?.detail;
			if (n && Ou(n.preference) && ku(n.resolved)) {
				t(n);
				return;
			}
			t(Au());
		};
		return window.addEventListener("folio:theme-changed", e), e(), () => window.removeEventListener("folio:theme-changed", e);
	}, []), {
		...e,
		setPreference(e) {
			let n = window.FolioTheme?.setPreference(e);
			t(n || {
				preference: e,
				resolved: e === "system" ? Au().resolved : e
			});
		}
	};
}
//#endregion
//#region src/app/WorkLogMigration.tsx
function Mu(e) {
	return e instanceof F ? e.code || `http_${e.status}` : e instanceof Error && /^[a-z0-9_]+$/.test(e.message) ? e.message : "request_failed";
}
function Nu(e) {
	let t = new Date(e);
	return Number.isNaN(t.getTime()) ? "시간 확인 불가" : new Intl.DateTimeFormat("ko-KR", {
		dateStyle: "short",
		timeStyle: "short"
	}).format(t);
}
function Pu() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)("migrate_keep_original"), [i, a] = (0, l.useState)(!1), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(""), d = (0, l.useRef)(!1), f = (0, l.useRef)(null), p = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		if (!e) return;
		f.current?.querySelector("button:not([disabled]), input:not([disabled])")?.focus();
		let t = (e) => {
			if (e.key === "Escape" && m(), e.key !== "Tab" || !f.current) return;
			let t = Array.from(f.current.querySelectorAll("button:not([disabled]), input:not([disabled])"));
			if (!t.length) return;
			let n = t[0], r = t[t.length - 1];
			e.shiftKey && document.activeElement === n ? (e.preventDefault(), r.focus()) : !e.shiftKey && document.activeElement === r && (e.preventDefault(), n.focus());
		};
		return document.addEventListener("keydown", t), () => document.removeEventListener("keydown", t);
	}, [e]);
	function m() {
		t(null), s(""), window.setTimeout(() => p.current?.focus(), 0);
	}
	async function h(e) {
		if (!d.current) {
			d.current = !0, p.current = e, a(!0), s(""), u("");
			try {
				let e = await V("/api/agent/work-log/migration-preview", {});
				t(e), r("migrate_keep_original");
			} catch (e) {
				s(Mu(e));
			} finally {
				d.current = !1, a(!1);
			}
		}
	}
	async function g() {
		if (!(!e || d.current || e.collisions.length > 0)) {
			d.current = !0, a(!0), s("");
			try {
				let t = await V("/api/agent/work-log/migration-confirm", {
					previewToken: e.previewToken,
					action: n
				});
				u(`${t.migratedJobs}건을 가져왔습니다.`), m();
			} catch (e) {
				t(null), s(Mu(e));
			} finally {
				d.current = !1, a(!1);
			}
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "work-log-migration-control",
		children: [
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "filter-actions settings-actions",
				children: /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					"data-qa": "work-log-migration-preview",
					disabled: i,
					onClick: (e) => void h(e.currentTarget),
					children: i && !e ? "확인 중" : "이전 작업 기록 가져오기"
				})
			}),
			o && /* @__PURE__ */ (0, K.jsxs)("p", {
				className: "react-dashboard-error",
				"data-qa": "work-log-migration-error",
				"data-error-code": o,
				children: [
					"마이그레이션을 완료하지 못했습니다. 다시 미리보세요. (",
					o,
					")"
				]
			}),
			c && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				"data-qa": "work-log-migration-success",
				role: "status",
				children: c
			}),
			e && /* @__PURE__ */ (0, K.jsx)("div", {
				className: "work-log-dialog-backdrop",
				children: /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "work-log-dialog",
					ref: f,
					role: "dialog",
					"aria-modal": "true",
					"aria-labelledby": "work-log-migration-title",
					"data-qa": "work-log-migration-dialog",
					children: [
						/* @__PURE__ */ (0, K.jsx)("h3", {
							id: "work-log-migration-title",
							children: "이전 작업 기록 가져오기"
						}),
						/* @__PURE__ */ (0, K.jsxs)("p", {
							"data-qa": "work-log-migration-summary",
							children: [
								"이전 ",
								e.legacyJobs,
								"건 · 가져올 수 있음 ",
								e.migratableJobs,
								"건 · ",
								Nu(e.expiresAt),
								"까지"
							]
						}),
						e.collisions.length > 0 && /* @__PURE__ */ (0, K.jsxs)("p", {
							className: "react-dashboard-error",
							"data-qa": "work-log-migration-collisions",
							children: [
								"충돌 ",
								e.collisions.length,
								"건이 있어 진행할 수 없습니다."
							]
						}),
						/* @__PURE__ */ (0, K.jsxs)("label", { children: [/* @__PURE__ */ (0, K.jsx)("input", {
							type: "radio",
							name: "migration-action",
							"data-qa": "work-log-migration-keep",
							checked: n === "migrate_keep_original",
							onChange: () => r("migrate_keep_original")
						}), " 원본 유지"] }),
						/* @__PURE__ */ (0, K.jsxs)("label", { children: [/* @__PURE__ */ (0, K.jsx)("input", {
							type: "radio",
							name: "migration-action",
							"data-qa": "work-log-migration-delete-original",
							checked: n === "migrate_delete_original",
							onChange: () => r("migrate_delete_original")
						}), " 성공 후 이전 jobs 파일 삭제"] }),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "work-log-dialog-actions",
							children: [/* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"data-qa": "work-log-migration-confirm",
								disabled: i || e.collisions.length > 0,
								onClick: () => void g(),
								children: "가져오기 확인"
							}), /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"data-qa": "work-log-migration-cancel",
								onClick: m,
								children: "취소"
							})]
						})
					]
				})
			})
		]
	});
}
//#endregion
//#region src/app/SettingsRoute.tsx
var Fu = [{
	id: "admin",
	label: "관리"
}, {
	id: "integrations",
	label: "연동"
}], Iu = [
	"openai",
	"gemini",
	"claude"
], Lu = {
	openai: {
		name: "OpenAI",
		key: "sk-...",
		model: "gpt-5.5"
	},
	gemini: {
		name: "Gemini",
		key: "AIza...",
		model: "gemini-3.5-flash"
	},
	claude: {
		name: "Claude",
		key: "sk-ant-...",
		model: "claude-sonnet-5"
	}
};
function Ru(e) {
	return Iu.includes(e) ? e : "openai";
}
function zu(e, t) {
	let n = t || [];
	return n.some((t) => t.value === e) ? String(e || "") : n[0]?.value || "";
}
function Bu(e, t, n, r) {
	return e ? `${r} 저장됨: ${t || "저장됨"}` : n;
}
function Vu({ checked: e, onChange: t, label: n, ariaLabel: r, compact: i = !1, disabled: a = !1, title: o }) {
	return /* @__PURE__ */ (0, K.jsxs)("label", {
		className: `settings-switch${i ? " settings-switch-compact" : ""}${e ? " is-on" : ""}${a ? " is-disabled" : ""}`,
		title: o,
		children: [
			/* @__PURE__ */ (0, K.jsx)("input", {
				"aria-label": r || n || "설정 전환",
				checked: e,
				disabled: a,
				onChange: (e) => t(e.currentTarget.checked),
				type: "checkbox"
			}),
			/* @__PURE__ */ (0, K.jsx)("span", {
				className: "settings-switch-track",
				"aria-hidden": "true",
				children: /* @__PURE__ */ (0, K.jsx)("span", { className: "settings-switch-thumb" })
			}),
			n ? /* @__PURE__ */ (0, K.jsxs)("span", {
				className: "settings-switch-copy",
				children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: n }), /* @__PURE__ */ (0, K.jsx)("small", { children: e ? "ON" : "OFF" })]
			}) : /* @__PURE__ */ (0, K.jsx)("span", {
				className: "settings-switch-state",
				"aria-hidden": "true",
				children: e ? "ON" : "OFF"
			})
		]
	});
}
function Hu(e) {
	return {
		rss: {
			enabled: !!e.rss?.enabled,
			intervalMinutes: e.rss?.intervalMinutes || 60,
			saveFullText: e.rss?.saveFullText !== !1,
			retentionDays: e.rss?.retentionDays ?? ed
		},
		marketMemory: {
			enabled: !!e.marketMemory?.enabled,
			intervalMinutes: e.marketMemory?.intervalMinutes || 1440,
			runAfterRss: !!e.marketMemory?.runAfterRss
		},
		briefingSchedules: (e.briefingSchedules || []).slice(0, Uu).map((e) => ({
			id: e.id,
			enabled: !!e.enabled,
			time: e.time || "08:00",
			markets: [...e.markets || []],
			briefingType: e.briefingType || "default",
			kind: e.kind === "weekly" ? "weekly" : "daily",
			qualityMode: e.qualityMode || "diagnose_only",
			runPrerequisites: !!e.runPrerequisites,
			...e.days ? { days: [...e.days] } : {}
		})),
		missedRuns: { catchUpHours: e.missedRuns?.catchUpHours ?? 3 }
	};
}
var Uu = 5, Wu = [
	{
		id: 0,
		label: "월"
	},
	{
		id: 1,
		label: "화"
	},
	{
		id: 2,
		label: "수"
	},
	{
		id: 3,
		label: "목"
	},
	{
		id: 4,
		label: "금"
	},
	{
		id: 5,
		label: "토"
	},
	{
		id: 6,
		label: "일"
	}
], Gu = Wu.map((e) => e.id);
function Ku(e) {
	return e.days ?? Gu;
}
var qu = [
	{
		id: "us",
		label: "US"
	},
	{
		id: "kr",
		label: "KR"
	},
	{
		id: "europe",
		label: "EU"
	},
	{
		id: "jp",
		label: "JP"
	}
], Ju = Object.fromEntries(qu.flatMap((e) => [[e.id, e.label], [e.id.toUpperCase(), e.label]])), Yu = [
	{
		label: "아침",
		time: "08:00",
		markets: ["us", "europe"],
		hint: "밤사이 해외장"
	},
	{
		label: "저녁",
		time: "18:00",
		markets: ["kr", "jp"],
		hint: "오늘 국내장"
	},
	{
		label: "주말",
		time: "09:00",
		markets: [
			"us",
			"kr",
			"europe",
			"jp"
		],
		hint: "지난주 요약과 다음주 일정",
		kind: "weekly",
		days: [6]
	}
], Xu = {
	daily: "일간",
	weekly: "주간 요약"
};
function Zu(e) {
	return e.kind === "weekly" ? "weekly" : "daily";
}
function Qu() {
	return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}
var $u = [
	{
		value: "0",
		label: "정시에만"
	},
	{
		value: "1",
		label: "1시간 안이면"
	},
	{
		value: "3",
		label: "3시간 안이면"
	},
	{
		value: "6",
		label: "6시간 안이면"
	},
	{
		value: "24",
		label: "그날 안이면 언제든"
	}
], ed = 90, td = [
	{
		value: "30",
		label: "30일"
	},
	{
		value: "60",
		label: "60일"
	},
	{
		value: "90",
		label: "90일"
	},
	{
		value: "180",
		label: "180일"
	},
	{
		value: "365",
		label: "1년"
	},
	{
		value: "0",
		label: "계속 보관"
	}
];
function nd({ note: e, panel: t }) {
	return !e || e.panel !== t ? null : /* @__PURE__ */ (0, K.jsx)("p", {
		className: e.tone === "error" ? "react-dashboard-error" : "react-dashboard-warning",
		role: "status",
		children: e.text
	});
}
function rd(e) {
	return `${Math.max(e / 1e6, 0).toFixed(e >= 1e8 ? 0 : 1)}MB`;
}
var id = 5e7;
function ad(e) {
	return (e || 0) >= id ? `검색 색인에서 약 ${rd(e)}를 돌려받습니다. 그동안 검색이 잠시 멈춥니다.` : "정리 후 검색 색인을 다시 만들고 파일 크기를 줄입니다. 몇 분 걸릴 수 있습니다.";
}
function od({ preview: e, days: t }) {
	return t <= 0 ? /* @__PURE__ */ (0, K.jsx)("p", {
		className: "settings-hint",
		children: "모든 자료를 계속 보관합니다. 수집이 쌓이는 만큼 검색 색인이 커집니다."
	}) : !e || e.days !== t ? /* @__PURE__ */ (0, K.jsx)("p", {
		className: "settings-hint",
		children: "정리 대상을 확인하는 중입니다."
	}) : e.files ? /* @__PURE__ */ (0, K.jsxs)("p", {
		className: "settings-hint",
		children: [
			e.cutoff,
			"보다 오래된 ",
			/* @__PURE__ */ (0, K.jsxs)("strong", { children: [e.files.toLocaleString(), "건"] }),
			"이 지워집니다",
			" ",
			"(자료 ",
			rd(e.fileBytes),
			", 검색 색인 약 ",
			rd(e.estimatedIndexBytes),
			")."
		]
	}) : /* @__PURE__ */ (0, K.jsxs)("p", {
		className: "settings-hint",
		children: [
			"지금은 ",
			e.cutoff,
			"보다 오래된 자료가 없어 지워지는 것이 없습니다."
		]
	});
}
function sd(e) {
	if (!e) return {
		tone: "",
		text: "아직 실행된 적 없습니다"
	};
	let t = e.finishedAt ? new Date(e.finishedAt) : null, n = t && !Number.isNaN(t.getTime()) ? t.toLocaleString("ko-KR", {
		month: "numeric",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit"
	}) : "";
	if (e.status === "failed") {
		let t = e.errorReason || "";
		return {
			tone: "is-failed",
			text: `${n} 실패${t ? ` — ${t}` : ""}`
		};
	}
	return e.status === "submitted" ? {
		tone: "",
		text: `${n} 제출됨 — 생성 중`
	} : {
		tone: "is-done",
		text: `${n} 완료`
	};
}
function cd({ schedules: e, watched: t, runsById: n, onChange: r }) {
	let i = (t, n) => r(e.map((e) => e.id === t ? {
		...e,
		...n
	} : e)), a = (e, t) => {
		let n = e.markets.includes(t) ? e.markets.filter((e) => e !== t) : qu.map((e) => e.id).filter((n) => n === t || e.markets.includes(n));
		i(e.id, {
			markets: n,
			...n.length ? {} : { enabled: !1 }
		});
	}, o = (e, t) => {
		let n = Ku(e), r = n.includes(t) ? n.filter((e) => e !== t) : Gu.filter((e) => e === t || n.includes(e));
		i(e.id, {
			days: r,
			...r.length ? {} : { enabled: !1 }
		});
	}, s = (t, n, i = "daily", a = [
		0,
		1,
		2,
		3,
		4
	]) => {
		e.length >= Uu || r([...e, {
			id: Qu(),
			enabled: !0,
			time: n,
			markets: t,
			briefingType: "default",
			kind: i,
			qualityMode: "diagnose_only",
			runPrerequisites: !0,
			days: [...a]
		}]);
	}, c = Yu.map((e) => ({
		...e,
		markets: e.markets.filter((e) => t.includes(e))
	})).filter((e) => e.markets.length);
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "schedule-list",
		children: [
			e.map((s) => {
				let c = s.markets.filter((e) => !t.includes(e));
				return /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "schedule-row",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "schedule-row-head",
							children: [
								/* @__PURE__ */ (0, K.jsx)("input", {
									type: "time",
									"aria-label": "브리핑 시각",
									value: s.time,
									onChange: (e) => i(s.id, { time: e.currentTarget.value })
								}),
								/* @__PURE__ */ (0, K.jsx)("select", {
									"aria-label": "브리핑 종류",
									value: Zu(s),
									onChange: (e) => i(s.id, { kind: e.currentTarget.value }),
									children: Object.entries(Xu).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
										value: e,
										children: t
									}, e))
								}),
								Zu(s) === "daily" && /* @__PURE__ */ (0, K.jsx)("select", {
									"aria-label": "브리핑 유형",
									value: s.briefingType,
									onChange: (e) => i(s.id, { briefingType: e.currentTarget.value }),
									children: Object.entries(ud).map(([e, t]) => /* @__PURE__ */ (0, K.jsx)("option", {
										value: e,
										children: t
									}, e))
								}),
								/* @__PURE__ */ (0, K.jsx)(Vu, {
									ariaLabel: `${s.time} 예약 사용`,
									checked: s.enabled,
									onChange: (e) => i(s.id, { enabled: e }),
									disabled: !s.markets.length || !Ku(s).length,
									title: s.markets.length ? Ku(s).length ? void 0 : "요일을 하나 이상 골라야 켤 수 있습니다." : "시장을 하나 이상 골라야 켤 수 있습니다.",
									compact: !0
								}),
								/* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn btn--quiet",
									type: "button",
									onClick: () => r(e.filter((e) => e.id !== s.id)),
									children: "삭제"
								})
							]
						}),
						/* @__PURE__ */ (0, K.jsx)("div", {
							className: "settings-theme-options",
							role: "group",
							"aria-label": `${s.time} 예약의 시장`,
							children: qu.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"aria-pressed": s.markets.includes(e.id),
								onClick: () => a(s, e.id),
								children: e.label
							}, e.id))
						}),
						Zu(s) === "weekly" && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "settings-hint",
							children: "고른 요일에 그 날짜까지의 지난 7일을 요약하고 다음주 일정을 붙입니다."
						}),
						/* @__PURE__ */ (0, K.jsx)("div", {
							className: "settings-theme-options",
							role: "group",
							"aria-label": `${s.time} 예약이 도는 요일`,
							children: Wu.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
								type: "button",
								"aria-pressed": Ku(s).includes(e.id),
								onClick: () => o(s, e.id),
								children: e.label
							}, e.id))
						}),
						/* @__PURE__ */ (0, K.jsxs)("div", {
							className: "automation-inline-switch",
							children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "브리핑 전에 RSS 수집과 시장 메모리 갱신" }), /* @__PURE__ */ (0, K.jsx)(Vu, {
								ariaLabel: `${s.time} 예약: 브리핑 전 RSS 수집과 시장 메모리 갱신`,
								checked: s.runPrerequisites !== !1,
								onChange: (e) => i(s.id, { runPrerequisites: e }),
								compact: !0
							})]
						}),
						c.length > 0 && /* @__PURE__ */ (0, K.jsxs)("p", {
							className: "settings-hint",
							children: [
								"관심 시장에서 꺼둔 ",
								c.map((e) => qu.find((t) => t.id === e)?.label || e).join(" · "),
								"은(는) 빼고 생성합니다."
							]
						}),
						/* @__PURE__ */ (0, K.jsx)(ld, { run: n[s.id] })
					]
				}, s.id);
			}),
			!e.length && c.length > 0 && /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "schedule-proposals",
				children: [/* @__PURE__ */ (0, K.jsx)("p", {
					className: "settings-hint",
					children: "아직 예약이 없습니다. 관심 시장의 마감 시각에 맞춰 제안합니다."
				}), c.map((e) => /* @__PURE__ */ (0, K.jsxs)("button", {
					className: "btn",
					type: "button",
					onClick: () => s(e.markets, e.time, e.kind || "daily", e.days || [
						0,
						1,
						2,
						3,
						4
					]),
					children: [
						e.label,
						" ",
						e.time,
						" — ",
						e.markets.map((e) => qu.find((t) => t.id === e)?.label).join(" · "),
						/* @__PURE__ */ (0, K.jsx)("span", { children: e.hint })
					]
				}, `${e.time}-${e.kind || "daily"}`))]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "schedule-actions",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					disabled: e.length >= Uu,
					onClick: () => s(t.length ? [...t] : qu.map((e) => e.id), "08:00"),
					children: "예약 추가"
				}), e.length >= Uu && /* @__PURE__ */ (0, K.jsxs)("span", {
					className: "settings-hint",
					children: [
						"최대 ",
						Uu,
						"개까지 만들 수 있습니다."
					]
				})]
			})
		]
	});
}
function ld({ run: e }) {
	let { tone: t, text: n } = sd(e);
	return /* @__PURE__ */ (0, K.jsxs)("p", {
		className: `automation-last-run ${t}`.trim(),
		children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "마지막 실행" }), n]
	});
}
var ud = {
	default: "기본",
	market_focused: "시황 중심",
	concise: "요약"
};
function dd() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)([]), [i, a] = (0, l.useState)(!1), [o, s] = (0, l.useState)("");
	if ((0, l.useEffect)(() => {
		let e = !1;
		return (async () => {
			try {
				let n = await B("/api/market-scope");
				if (e) return;
				t(n), r([...n.selected]);
			} catch {
				e || s("관심 시장 설정을 불러오지 못했습니다.");
			}
		})(), () => {
			e = !0;
		};
	}, []), !e) return null;
	let c = (t) => {
		r((n) => {
			let r = n.includes(t) ? n.filter((e) => e !== t) : [...n, t];
			return r.length ? e.markets.map((e) => e.id).filter((e) => r.includes(e)) : n;
		});
	}, u = JSON.stringify(n) !== JSON.stringify([...e.selected]), d = async () => {
		if (!u) {
			s("변경 사항이 없습니다.");
			return;
		}
		a(!0), s("");
		try {
			let e = await te("/api/market-scope", { selected: n });
			t(e), r([...e.selected]);
			let i = e.newlyEnabled || [];
			s(i.length ? "저장했습니다. 방금 켠 시장의 자료 수집을 시작했습니다 — 꺼져 있던 기간의 기사는 피드가 아직 내어주는 범위까지만 들어옵니다." : "저장했습니다.");
		} catch (e) {
			s(e instanceof Error ? e.message : "저장하지 못했습니다.");
		} finally {
			a(!1);
		}
	};
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "settings-panel input-panel",
		"data-qa": "market-scope-panel",
		children: [
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "input-panel-header",
				children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "관심 시장" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "여기서 끈 시장은 자료 수집이 멈추고 화면 전체(RSS·브리핑·캘린더·내러티브)에서 숨습니다. 유가·달러 같은 글로벌 자료는 항상 보입니다." })] })
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "field",
				children: [/* @__PURE__ */ (0, K.jsx)("span", {
					id: "marketScopeLabel",
					children: "수집·표시할 시장"
				}), /* @__PURE__ */ (0, K.jsx)("div", {
					className: "settings-theme-options",
					role: "group",
					"aria-labelledby": "marketScopeLabel",
					children: e.markets.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						"aria-pressed": n.includes(e.id),
						disabled: i,
						onClick: () => c(e.id),
						"aria-label": e.label,
						children: Ju[e.id] || e.label
					}, e.id))
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "settings-actions",
				children: [u && !i && /* @__PURE__ */ (0, K.jsx)("span", {
					className: "settings-dirty-hint",
					children: "저장 안 된 변경"
				}), /* @__PURE__ */ (0, K.jsx)("button", {
					className: u && !i ? "btn btn--primary" : "btn",
					type: "button",
					onClick: () => void d(),
					disabled: i,
					children: i ? "저장 중" : "저장"
				})]
			}),
			o && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				role: "status",
				children: o
			})
		]
	});
}
function fd(e) {
	let t = [
		"B",
		"KB",
		"MB",
		"GB"
	], n = Math.max(0, e), r = 0;
	for (; n >= 1024 && r < t.length - 1;) n /= 1024, r += 1;
	return r === 0 ? `${Math.round(n)} B` : `${n.toFixed(1)} ${t[r]}`;
}
function pd() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)(""), [i, a] = (0, l.useState)(""), [o, s] = (0, l.useState)(""), c = (0, l.useCallback)(async () => {
		try {
			t(await B("/api/workspace"));
		} catch {
			a("자료 위치를 읽지 못했습니다.");
		}
	}, []);
	if ((0, l.useEffect)(() => {
		c();
	}, [c]), !e) return null;
	let u = async (e, t) => {
		r(e), a("");
		try {
			let n = await V("/api/workspace/move", {
				destination: e,
				merge: t
			});
			s(""), await c(), a(`자료 ${n.fileCount}개를 ${n.path}(으)로 복사했습니다. 서버를 재시작해야 새 위치를 사용합니다. 원본은 ${n.previousPath}에 그대로 있으니 새 위치에서 자료가 잘 보이는지 확인한 뒤 지우세요. 재시작 전까지는 RSS 수집과 보관 기간 정리가 일시정지됩니다.`);
		} catch (t) {
			let n = t instanceof Error ? t.message : "옮기지 못했습니다.";
			n.includes("이미 자료") && s(e), a(n);
		} finally {
			r("");
		}
	}, d = async () => {
		r("reveal");
		try {
			await V("/api/workspace/reveal", {});
		} catch (e) {
			a(e instanceof Error ? e.message : "폴더를 열지 못했습니다.");
		} finally {
			r("");
		}
	};
	return /* @__PURE__ */ (0, K.jsxs)("section", {
		className: "settings-panel input-panel",
		"data-qa": "workspace-panel",
		children: [
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "input-panel-header",
				children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "자료 위치" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "보고서·수집 자료·설정이 저장되는 폴더입니다. 새 버전은 버전 이름이 붙은 새 폴더로 풀리기 때문에, 자료가 앱 폴더 안에 있으면 업데이트할 때 직접 옮겨야 합니다." })] })
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "field",
				children: [
					/* @__PURE__ */ (0, K.jsx)("span", {
						id: "workspacePathLabel",
						children: "지금 쓰는 폴더"
					}),
					/* @__PURE__ */ (0, K.jsx)("p", {
						className: "workspace-path",
						"aria-labelledby": "workspacePathLabel",
						children: e.path
					}),
					/* @__PURE__ */ (0, K.jsxs)("p", {
						className: "settings-hint",
						children: [
							"자료 ",
							e.fileCount.toLocaleString(),
							"개 · ",
							fd(e.totalBytes),
							e.outsideAppFolder ? " · 앱 폴더 밖에 있어 새 버전을 받아도 그대로 이어집니다." : " · 앱 폴더 안에 있습니다."
						]
					})
				]
			}),
			e.envPinned && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "settings-hint",
				children: "FOLIO_HOME 환경변수가 이 위치를 정하고 있습니다. 여기서 옮기려면 환경변수를 먼저 지우세요."
			}),
			e.documentsIsOneDrive && e.canMoveToDocuments && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				role: "status",
				children: "문서 폴더가 OneDrive와 동기화됩니다. 자료에는 700MB가 넘는 검색 인덱스가 있어 저장할 때마다 업로드가 돌고, 두 PC에서 함께 쓰면 충돌 사본이 생길 수 있습니다."
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "settings-actions",
				children: [
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => window.dispatchEvent(new CustomEvent("folio:show-welcome")),
						children: "첫 실행 안내 다시 보기"
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => void d(),
						disabled: !!n,
						children: n === "reveal" ? "여는 중" : "폴더 열기"
					}),
					e.canMoveToDocuments && e.documentsAvailable && /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "button",
						onClick: () => void u("documents", o === "documents"),
						disabled: !!n,
						children: n === "documents" ? "복사 중" : o === "documents" ? "그래도 합치기" : "문서 폴더로 옮기기"
					}),
					e.canMoveToAppFolder && /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: () => void u("app", o === "app"),
						disabled: !!n,
						children: n === "app" ? "복사 중" : o === "app" ? "그래도 합치기" : "앱 폴더로 되돌리기"
					})
				]
			}),
			e.canMoveToDocuments && e.documentsAvailable && /* @__PURE__ */ (0, K.jsxs)("p", {
				className: "settings-hint",
				children: [
					"옮길 위치: ",
					e.documentsPath,
					" · 복사만 하고 원본은 지우지 않습니다."
				]
			}),
			i && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				role: "status",
				children: i
			})
		]
	});
}
function md() {
	let e = ju(), t = Du(), [n, r] = (0, l.useState)("admin"), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(null), [c, u] = (0, l.useState)({}), [d, f] = (0, l.useState)({}), [p, m] = (0, l.useState)([]), [h, g] = (0, l.useState)(null), [_, v] = (0, l.useState)(qu.map((e) => e.id)), [y, b] = (0, l.useState)({}), [x, S] = (0, l.useState)(null), [C, w] = (0, l.useState)("openai"), [T, E] = (0, l.useState)(""), [D, O] = (0, l.useState)(""), [k, A] = (0, l.useState)(!0), [j, M] = (0, l.useState)("cli"), [N, P] = (0, l.useState)("codex"), [F, I] = (0, l.useState)(""), [L, R] = (0, l.useState)({
		fred: "",
		bok: "",
		dart: ""
	}), [z, H] = (0, l.useState)({
		token: "",
		dbId: ""
	}), [U, ee] = (0, l.useState)(""), [te, W] = (0, l.useState)({}), [G, q] = (0, l.useState)(""), [ne, re] = (0, l.useState)(null), ie = (0, l.useCallback)((e, t) => re({
		panel: e,
		text: t,
		tone: "ok"
	}), []), ae = (0, l.useCallback)((e, t) => re({
		panel: e,
		text: t,
		tone: "error"
	}), []), [oe, se] = (0, l.useState)(""), ce = i?.llm?.providers || {}, le = ce[C] || {}, ue = Lu[C], de = le.modelChoices || [], fe = o?.adapters || [], pe = (fe.find((e) => e.id === N) || fe[0])?.modelChoices || [], me = [
		"codex",
		"claude",
		"antigravity"
	].includes(o?.provider || "") ? String(o?.provider) : String(o?.selectedAdapter || fe[0]?.id || "codex"), he = fe.find((e) => e.id === me) || fe[0], ge = k !== (i?.agent?.enabled !== !1) || j !== (i?.agent?.mode === "api" ? "api" : "cli") || N !== me || F !== zu(he?.model, he?.modelChoices) || C !== Ru(i?.llm?.provider) || D !== zu(le.model, le.modelChoices) || T.trim() !== "", _e = !!(L.fred.trim() || L.bok.trim() || L.dart.trim()), ve = !!z.token.trim() || z.dbId.trim() !== String(i?.notion?.dbId || "").trim(), ye = U.trim() !== String(y.vaultPath || "").trim(), be = JSON.stringify(Hu(c)) !== JSON.stringify(Hu(d)), xe = (0, l.useMemo)(() => {
		let e = {};
		for (let t of p) {
			let n = String(t.kind || "");
			n && !e[n] && (e[n] = t);
		}
		return e;
	}, [p]), Se = (0, l.useMemo)(() => {
		let e = {};
		for (let t of p) {
			if (t.kind !== "briefing") continue;
			let n = String(t.scheduleId || "");
			n && !e[n] && (e[n] = t);
		}
		return e;
	}, [p]), Ce = (0, l.useCallback)(async (e = !1) => {
		se(""), q("load");
		try {
			let [t, n, r, i, o, c] = await Promise.all([
				B(`/api/settings${e ? "?refresh=true" : ""}`),
				B(`/api/agent-bridge/settings${e ? "?refresh=true" : ""}`),
				B("/api/automation/settings"),
				B("/api/obsidian/settings"),
				B("/api/automation/runs?limit=50").catch(() => ({ items: [] })),
				B("/api/market-scope").catch(() => null)
			]);
			m(o.items || []), c?.selected && v(c.selected.map((e) => String(e).toLowerCase())), a(t), A(t.agent?.enabled !== !1), M(t.agent?.mode === "api" ? "api" : "cli");
			let l = Ru(t.llm?.provider);
			w(l);
			let d = t.llm?.providers?.[l] || {}, p = d.modelChoices || [];
			O(p.some((e) => e.value === d.model) ? String(d.model || "") : p[0]?.value || ""), H({
				token: "",
				dbId: t.notion?.dbId || ""
			}), s(n);
			let h = [
				"codex",
				"claude",
				"antigravity"
			].includes(n.provider || "") ? String(n.provider) : String(n.selectedAdapter || n.adapters?.[0]?.id || "codex"), g = n.adapters?.find((e) => e.id === h) || n.adapters?.[0];
			P(h);
			let _ = g?.modelChoices || [];
			I(_.some((e) => e.value === g?.model) ? String(g?.model || "") : _[0]?.value || ""), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: n })), u(Hu(r)), f(Hu(r)), b(i), ee(i.vaultPath || ""), Qe("settings", {
				surface: "settings",
				viewId: "settings",
				reportKind: "",
				reportId: ""
			});
		} catch (e) {
			se(e instanceof Error ? e.message : "설정을 불러오지 못했습니다.");
		} finally {
			q("");
		}
	}, []), we = (0, l.useCallback)(async () => {
		q("cache"), re(null);
		try {
			let e = await B("/api/cache/stats");
			S(e), ie("cache", "캐시 상태를 불러왔습니다.");
		} catch (e) {
			ae("cache", e instanceof Error ? e.message : "캐시 상태를 불러오지 못했습니다.");
		} finally {
			q("");
		}
	}, []);
	async function Te() {
		q("cache-cleanup"), ae("cache", ""), ie("cache", "오래된 기업 데이터 캐시를 정리하는 중입니다.");
		try {
			let e = await V("/api/cache/cleanup", {}), t = await B("/api/cache/stats");
			S(t), ie("cache", e.deleted ? `캐시 정리 완료: ${e.deleted}개 삭제, ${e.freed_mb || 0}MB 확보` : "정리할 오래된 캐시가 없습니다. 보관 기간이 지난 파일만 지웁니다.");
		} catch (e) {
			ae("cache", e instanceof Error ? e.message : "캐시 정리에 실패했습니다.");
		} finally {
			q("");
		}
	}
	let Ee = Number(c.rss?.retentionDays ?? ed);
	(0, l.useEffect)(() => {
		if (Ee <= 0) return;
		let e = !0;
		return B(`/api/rss/retention?days=${Ee}`).then((t) => {
			e && g(t);
		}).catch(() => {
			e && g(null);
		}), () => {
			e = !1;
		};
	}, [Ee]);
	async function De() {
		q("retention"), ae("automation", "");
		try {
			await V("/api/rss/retention/run", {}), ie("automation", "정리 작업을 시작했습니다. 진행 상황은 상단 작업 표시에서 확인합니다.");
		} catch (e) {
			ae("automation", e instanceof Error ? e.message : "정리를 시작하지 못했습니다.");
		} finally {
			q("");
		}
	}
	(0, l.useEffect)(() => {
		Ce();
	}, [Ce]), (0, l.useEffect)(() => {
		let e = ce[C] || {}, t = e.modelChoices || [];
		O((n) => t.some((e) => e.value === n) ? n : t.some((t) => t.value === e.model) ? String(e.model || "") : t[0]?.value || ""), E("");
	}, [C, ce]), (0, l.useEffect)(() => {
		let e = fe.find((e) => e.id === N) || fe[0], t = e?.modelChoices || [];
		I((n) => t.some((e) => e.value === n) ? n : t.some((t) => t.value === e?.model) ? String(e?.model || "") : t[0]?.value || "");
	}, [N, fe]);
	async function Oe() {
		if (!ge) {
			ie("agent", "변경 사항이 없습니다.");
			return;
		}
		q("agent"), ie("agent", "AI Agent 설정을 저장하는 중입니다.");
		try {
			let e = Object.fromEntries(fe.map((e) => [e.id, e.model || ""]));
			e[N] = F;
			let [t, n] = await Promise.all([V("/api/agent-bridge/settings", {
				provider: N,
				models: e
			}), V("/api/settings", {
				agent: {
					enabled: k,
					mode: j
				},
				llm: {
					provider: C,
					providers: { [C]: {
						apiKey: T.trim(),
						model: D
					} }
				}
			})]);
			s(t), a(n), E(""), W((e) => {
				let t = { ...e };
				return delete t[C], t;
			}), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: t })), ie("agent", k ? `AI Agent를 ${j === "cli" ? "LLM CLI" : "LLM API"} 모드로 저장했습니다.` : "AI Agent 생성을 비활성화했습니다.");
		} catch (e) {
			ae("agent", e instanceof Error ? e.message : "AI Agent 설정 저장에 실패했습니다.");
		} finally {
			q("");
		}
	}
	async function ke(e) {
		if (!ce[e]?.hasApiKey) {
			W((t) => ({
				...t,
				[e]: {
					status: "missing_key",
					available: !1,
					message: "API 키를 먼저 입력하세요"
				}
			}));
			return;
		}
		W((t) => ({
			...t,
			[e]: { checking: !0 }
		}));
		try {
			let t = await V(`/api/settings/llm/test/${encodeURIComponent(e)}`, {});
			W((n) => ({
				...n,
				[e]: t
			}));
		} catch (t) {
			W((n) => ({
				...n,
				[e]: {
					status: "network_error",
					available: !1,
					message: t instanceof Error ? t.message : "연결 확인 실패"
				}
			}));
		}
	}
	async function Ae() {
		if (!_e) {
			ie("api", "변경 사항이 없습니다.");
			return;
		}
		q("api"), ie("api", "외부 데이터 API 설정을 저장하는 중입니다.");
		try {
			let e = await V("/api/settings", {
				fred: { apiKey: L.fred.trim() },
				bok: { apiKey: L.bok.trim() },
				dart: { apiKey: L.dart.trim() }
			});
			a(e), R({
				fred: "",
				bok: "",
				dart: ""
			}), ie("api", "외부 데이터 API 설정을 저장했습니다.");
		} catch (e) {
			ae("api", e instanceof Error ? e.message : "API 설정 저장에 실패했습니다.");
		} finally {
			q("");
		}
	}
	async function je() {
		if (!ve) {
			ie("notion", "변경 사항이 없습니다.");
			return;
		}
		q("notion"), ie("notion", "Notion 설정을 저장하는 중입니다.");
		try {
			let e = await V("/api/settings", { notion: {
				token: z.token.trim(),
				dbId: z.dbId.trim()
			} });
			a(e), H({
				token: "",
				dbId: e.notion?.dbId || ""
			}), ie("notion", "Notion 설정을 저장했습니다.");
		} catch (e) {
			ae("notion", e instanceof Error ? e.message : "Notion 설정 저장에 실패했습니다.");
		} finally {
			q("");
		}
	}
	async function Me() {
		if (!ye) {
			ie("obsidian", "변경 사항이 없습니다.");
			return;
		}
		q("obsidian"), ie("obsidian", "Obsidian 경로를 저장하는 중입니다.");
		try {
			let e = await V("/api/obsidian/settings", { vaultPath: U.trim() });
			b(e), ee(e.vaultPath || U), ie("obsidian", e.vaultPath ? "Obsidian 경로를 저장했습니다." : "Vault 경로를 입력하세요.");
		} catch (e) {
			ae("obsidian", e instanceof Error ? e.message : "Obsidian 설정 저장에 실패했습니다.");
		} finally {
			q("");
		}
	}
	async function Ne() {
		if (!be) {
			ie("automation", "변경 사항이 없습니다.");
			return;
		}
		q("automation"), ie("automation", "자동화 설정을 저장하는 중입니다.");
		try {
			let e = await V("/api/automation/settings", Hu(c));
			u(Hu(e)), f(Hu(e)), ie("automation", "자동화 설정을 저장했습니다.");
		} catch (e) {
			ae("automation", e instanceof Error ? e.message : "자동화 설정 저장에 실패했습니다.");
		} finally {
			q("");
		}
	}
	let Pe = (0, l.useMemo)(() => Iu.map((e) => {
		let t = ce[e] || {}, n = te[e], r = n?.checking;
		return {
			providerId: e,
			row: t,
			label: r ? "확인 중" : n?.available ? "사용 가능" : n ? "확인 실패" : t.hasApiKey ? "확인 필요" : "키 없음",
			className: n?.available ? "ready" : r || n ? "warn" : "",
			detail: n?.message || `${t.model || "모델 미설정"} · ${t.hasApiKey ? "저장된 키가 있습니다." : "API Key를 저장하세요."}`,
			checkedAt: du(n?.checkedAt)
		};
	}), [te, ce]);
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-settings-route",
		"data-settings-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Settings",
				title: "설정",
				description: "화면, 관심 시장, 자동화와 LLM·외부 데이터·내보내기 연동을 관리합니다.",
				actions: /* @__PURE__ */ (0, K.jsx)("button", {
					className: "btn",
					type: "button",
					onClick: () => Ce(!0),
					disabled: G === "load",
					children: G === "load" ? "불러오는 중" : "새로고침"
				})
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "segment settings-tabs",
				role: "group",
				"aria-label": "설정 하위 탭",
				children: Fu.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
					type: "button",
					"aria-pressed": n === e.id,
					onClick: () => r(e.id),
					children: e.label
				}, e.id))
			}),
			oe && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: oe
			}),
			n === "integrations" ? /* @__PURE__ */ (0, K.jsxs)("div", {
				id: "settings-integrations",
				className: "sub-tab-panel active",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsx)("div", {
								className: "input-panel-header settings-agent-header",
								children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "AI Agent 설정" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "보고서와 시장 내러티브 생성에 사용할 Agent 경로를 선택합니다. 비활성화하면 규칙 기반으로 생성합니다." })] })
							}),
							/* @__PURE__ */ (0, K.jsx)("div", {
								className: "settings-grid",
								children: /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [
										/* @__PURE__ */ (0, K.jsx)("span", { children: "실행 방식" }),
										/* @__PURE__ */ (0, K.jsxs)("div", {
											className: "settings-agent-mode-row",
											children: [/* @__PURE__ */ (0, K.jsx)(Vu, {
												ariaLabel: "AI Agent 사용",
												checked: k,
												onChange: A,
												compact: !0
											}), /* @__PURE__ */ (0, K.jsxs)("div", {
												className: "segment",
												role: "group",
												"aria-label": "AI Agent 실행 방식",
												children: [/* @__PURE__ */ (0, K.jsx)("button", {
													"aria-pressed": j === "cli",
													type: "button",
													onClick: () => M("cli"),
													children: "LLM CLI"
												}), /* @__PURE__ */ (0, K.jsx)("button", {
													"aria-pressed": j === "api",
													type: "button",
													onClick: () => M("api"),
													children: "LLM API"
												})]
											})]
										}),
										!k && /* @__PURE__ */ (0, K.jsx)("p", {
											className: "settings-hint",
											children: "AI Agent가 꺼져 있어요. 켜면 아래 설정을 쓸 수 있습니다."
										})
									]
								})
							}),
							/* @__PURE__ */ (0, K.jsx)("fieldset", {
								className: "settings-agent-controls",
								disabled: !k,
								children: j === "cli" ? /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsxs)("div", {
									className: "settings-grid",
									children: [/* @__PURE__ */ (0, K.jsxs)("label", {
										className: "field",
										children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "사용할 CLI" }), /* @__PURE__ */ (0, K.jsx)("select", {
											value: N,
											onChange: (e) => P(e.currentTarget.value),
											children: (fe.length ? fe : [
												{
													id: "codex",
													label: "Codex CLI"
												},
												{
													id: "claude",
													label: "Claude Code CLI"
												},
												{
													id: "antigravity",
													label: "Antigravity CLI"
												}
											]).map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
												value: e.id,
												children: e.label || e.id
											}, e.id))
										})]
									}), /* @__PURE__ */ (0, K.jsxs)("label", {
										className: "field",
										children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "모델" }), /* @__PURE__ */ (0, K.jsx)("select", {
											value: F,
											onChange: (e) => I(e.currentTarget.value),
											children: pe.length ? pe.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
												value: e.value,
												children: e.label
											}, e.value)) : /* @__PURE__ */ (0, K.jsx)("option", {
												value: "",
												children: "모델 목록 없음"
											})
										})]
									})]
								}), /* @__PURE__ */ (0, K.jsx)(pu, {
									adapters: fe,
									onSettings: (e) => s((t) => ({
										...t || {},
										...e
									}))
								})] }) : /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
									/* @__PURE__ */ (0, K.jsxs)("label", {
										className: "field",
										children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "API 제공자" }), /* @__PURE__ */ (0, K.jsxs)("select", {
											value: C,
											onChange: (e) => w(Ru(e.currentTarget.value)),
											children: [
												/* @__PURE__ */ (0, K.jsx)("option", {
													value: "openai",
													children: "GPT / OpenAI"
												}),
												/* @__PURE__ */ (0, K.jsx)("option", {
													value: "gemini",
													children: "Gemini / Google"
												}),
												/* @__PURE__ */ (0, K.jsx)("option", {
													value: "claude",
													children: "Claude / Anthropic"
												})
											]
										})]
									}),
									/* @__PURE__ */ (0, K.jsxs)("div", {
										className: "settings-grid",
										children: [/* @__PURE__ */ (0, K.jsxs)("label", {
											className: "field",
											children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [ue.name, " API Key"] }), /* @__PURE__ */ (0, K.jsx)("input", {
												value: T,
												onChange: (e) => E(e.currentTarget.value),
												type: "password",
												autoComplete: "off",
												placeholder: le.hasApiKey ? `${le.apiKeyMasked} 저장됨` : ue.key
											})]
										}), /* @__PURE__ */ (0, K.jsxs)("label", {
											className: "field",
											children: [/* @__PURE__ */ (0, K.jsxs)("span", { children: [ue.name, " Model"] }), /* @__PURE__ */ (0, K.jsx)("select", {
												value: D,
												onChange: (e) => O(e.currentTarget.value),
												children: de.length ? de.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
													value: e.value,
													children: e.label
												}, e.value)) : /* @__PURE__ */ (0, K.jsx)("option", {
													value: "",
													children: "모델 목록 없음"
												})
											})]
										})]
									}),
									/* @__PURE__ */ (0, K.jsx)("div", {
										className: "cli-provider-list",
										"aria-live": "polite",
										children: Pe.map(({ providerId: e, row: t, label: n, className: r, detail: i, checkedAt: a }) => /* @__PURE__ */ (0, K.jsxs)("div", {
											className: "cli-provider-row",
											children: [/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "cli-provider-main",
												children: [/* @__PURE__ */ (0, K.jsxs)("div", {
													className: "cli-provider-head",
													children: [
														/* @__PURE__ */ (0, K.jsx)("strong", { children: t.label || Lu[e].name }),
														/* @__PURE__ */ (0, K.jsx)("span", {
															className: `cli-chip status-chip ${r}`,
															children: n
														}),
														a && /* @__PURE__ */ (0, K.jsxs)("span", {
															className: "cli-provider-checked",
															children: [a, " 확인"]
														})
													]
												}), /* @__PURE__ */ (0, K.jsx)("div", {
													className: "cli-provider-meta",
													children: i
												})]
											}), /* @__PURE__ */ (0, K.jsxs)("div", {
												className: "cli-provider-actions",
												children: [/* @__PURE__ */ (0, K.jsx)("button", {
													className: "btn",
													type: "button",
													disabled: !!te[e]?.checking,
													onClick: () => ke(e),
													children: "연결 확인"
												}), t.setupUrl && /* @__PURE__ */ (0, K.jsx)("a", {
													className: "btn",
													href: t.setupUrl,
													target: "_blank",
													rel: "noreferrer",
													children: "콘솔 열기"
												})]
											})]
										}, e))
									}),
									/* @__PURE__ */ (0, K.jsxs)("p", {
										className: "cli-setup-note",
										children: [
											"이 앱은 키가 살아 있는지만 확인합니다. ",
											/* @__PURE__ */ (0, K.jsx)("b", { children: "사용량과 잔액은 제공사 콘솔" }),
											"에서 보세요."
										]
									})
								] })
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "filter-actions settings-actions",
								children: [
									ge && !G && /* @__PURE__ */ (0, K.jsx)("span", {
										className: "settings-dirty-hint",
										children: "저장 안 된 변경"
									}),
									/* @__PURE__ */ (0, K.jsx)("button", {
										className: ge && !G ? "btn btn--primary" : "btn",
										type: "button",
										onClick: Oe,
										disabled: G === "agent",
										children: "AI Agent 설정 저장"
									}),
									/* @__PURE__ */ (0, K.jsx)("button", {
										className: "btn",
										type: "button",
										onClick: () => Ce(!0),
										disabled: G === "load",
										children: "모델/상태 새로고침"
									})
								]
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "agent"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "API 연동" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "외부 데이터 API 키를 설정합니다." })]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "FRED API Key" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: L.fred,
										onChange: (e) => R({
											...L,
											fred: e.currentTarget.value
										}),
										type: "password",
										autoComplete: "off",
										placeholder: i?.fred?.hasApiKey ? `${i.fred.apiKeyMasked} 저장됨` : "FRED API 키"
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "FRED 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: Bu(i?.fred?.hasApiKey, i?.fred?.apiKeyMasked, "딥 리서치 미국 경제지표용 FRED API 키가 없습니다.", "FRED API 키")
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "BOK API Key" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: L.bok,
										onChange: (e) => R({
											...L,
											bok: e.currentTarget.value
										}),
										type: "password",
										autoComplete: "off",
										placeholder: i?.bok?.hasApiKey ? `${i.bok.apiKeyMasked} 저장됨` : "BOK ECOS API 키"
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "BOK 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: Bu(i?.bok?.hasApiKey, i?.bok?.apiKeyMasked, "딥 리서치 한국 경제지표용 BOK API 키가 없습니다.", "BOK API 키")
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "DART API Key" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: L.dart,
										onChange: (e) => R({
											...L,
											dart: e.currentTarget.value
										}),
										type: "password",
										autoComplete: "off",
										placeholder: i?.dart?.hasApiKey ? `${i.dart.apiKeyMasked} 저장됨` : "OpenDART API 키"
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "DART 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: Bu(i?.dart?.hasApiKey, i?.dart?.apiKeyMasked, "국내 기업 분석용 DART API 키가 없습니다.", "DART API 키")
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "filter-actions settings-actions",
								children: [_e && !G && /* @__PURE__ */ (0, K.jsx)("span", {
									className: "settings-dirty-hint",
									children: "저장 안 된 변경"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									className: _e && !G ? "btn btn--primary" : "btn",
									type: "button",
									onClick: Ae,
									disabled: G === "api",
									children: "API 설정 저장"
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "api"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "Notion 연동" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "브리핑과 보고서를 Notion 데이터베이스로 내보냅니다." })]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "Notion 통합 토큰" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: z.token,
										onChange: (e) => H({
											...z,
											token: e.currentTarget.value
										}),
										type: "password",
										autoComplete: "off",
										placeholder: i?.notion?.hasToken ? `${i.notion.tokenMasked} 저장됨` : "ntn_..."
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "토큰 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: i?.notion?.hasToken ? `토큰 저장됨: ${i.notion.tokenMasked}` : "Notion 통합 토큰이 없습니다."
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "데이터베이스 ID" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: z.dbId,
										onChange: (e) => H({
											...z,
											dbId: e.currentTarget.value
										}),
										placeholder: "32자리 Database ID"
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "DB 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: i?.notion?.hasDb ? `DB 저장됨: ${i.notion.dbIdMasked}` : "Notion 데이터베이스 ID가 없습니다."
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "filter-actions settings-actions",
								children: [ve && !G && /* @__PURE__ */ (0, K.jsx)("span", {
									className: "settings-dirty-hint",
									children: "저장 안 된 변경"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									className: ve && !G ? "btn btn--primary" : "btn",
									type: "button",
									onClick: je,
									disabled: G === "notion",
									children: "Notion 설정 저장"
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "notion"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "Obsidian 연동" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "원하면 Obsidian Vault로 보고서와 노트를 내보낼 수 있습니다." })]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "settings-grid",
								children: [/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "Vault 폴더 경로" }), /* @__PURE__ */ (0, K.jsx)("input", {
										value: U,
										onChange: (e) => ee(e.currentTarget.value),
										type: "text",
										placeholder: "C:\\Users\\username\\Documents\\MyVault"
									})]
								}), /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "경로 상태" }), /* @__PURE__ */ (0, K.jsx)("p", {
										className: "section-subtitle",
										children: y.vaultPath ? `설정됨: ${y.vaultPath}` : "Vault 경로가 설정되지 않았습니다."
									})]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "filter-actions settings-actions",
								children: [ye && !G && /* @__PURE__ */ (0, K.jsx)("span", {
									className: "settings-dirty-hint",
									children: "저장 안 된 변경"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									className: ye && !G ? "btn btn--primary" : "btn",
									type: "button",
									onClick: Me,
									disabled: G === "obsidian",
									children: "Obsidian 설정 저장"
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "obsidian"
							})
						]
					})
				]
			}) : /* @__PURE__ */ (0, K.jsxs)("div", {
				id: "settings-admin",
				className: "sub-tab-panel active",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						"data-display-settings": !0,
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "화면" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "이 브라우저의 색상 모드와 움직임 방식을 저장합니다." })] }), /* @__PURE__ */ (0, K.jsxs)("span", {
									className: "settings-theme-status",
									"aria-live": "polite",
									children: ["현재 ", e.resolved === "dark" ? "다크" : "라이트"]
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "field",
								children: [/* @__PURE__ */ (0, K.jsx)("span", {
									id: "themePreferenceLabel",
									children: "테마"
								}), /* @__PURE__ */ (0, K.jsx)("div", {
									className: "settings-theme-options",
									role: "group",
									"aria-labelledby": "themePreferenceLabel",
									children: [
										["light", "라이트"],
										["dark", "다크"],
										["system", "시스템"]
									].map(([t, n]) => /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": e.preference === t,
										onClick: () => e.setPreference(t),
										children: n
									}, t))
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)("div", {
								className: "settings-grid",
								children: /* @__PURE__ */ (0, K.jsxs)("label", {
									className: "field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "움직임" }), /* @__PURE__ */ (0, K.jsxs)("select", {
										value: t.preferences.motion,
										onChange: (e) => t.setMotion(e.currentTarget.value === "reduced" ? "reduced" : "system"),
										children: [/* @__PURE__ */ (0, K.jsx)("option", {
											value: "system",
											children: "시스템 설정 따르기"
										}), /* @__PURE__ */ (0, K.jsx)("option", {
											value: "reduced",
											children: "움직임 줄이기"
										})]
									})]
								})
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsx)(dd, {}),
					/* @__PURE__ */ (0, K.jsx)(pd, {}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "자동화" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "수집, 중기 시장 정리, 브리핑 생성을 각각 독립 루틴으로 관리합니다." })]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "automation-routines",
								children: [
									/* @__PURE__ */ (0, K.jsxs)("section", {
										className: "automation-card",
										children: [
											/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "automation-card-head",
												children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [
													/* @__PURE__ */ (0, K.jsx)("span", { children: "RSS Collection" }),
													/* @__PURE__ */ (0, K.jsx)("strong", { children: "RSS 수집" }),
													/* @__PURE__ */ (0, K.jsx)("p", { children: "뉴스 피드를 정해진 간격으로 가져와 research inbox와 인덱스에 반영합니다." })
												] }), /* @__PURE__ */ (0, K.jsx)(Vu, {
													ariaLabel: "RSS 자동 수집",
													checked: !!c.rss?.enabled,
													onChange: (e) => u({
														...c,
														rss: {
															...c.rss,
															enabled: e
														}
													}),
													compact: !0
												})]
											}),
											/* @__PURE__ */ (0, K.jsxs)("label", {
												className: "field",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "수집 간격" }), /* @__PURE__ */ (0, K.jsxs)("select", {
													value: String(c.rss?.intervalMinutes || 60),
													onChange: (e) => u({
														...c,
														rss: {
															...c.rss,
															intervalMinutes: e.currentTarget.value
														}
													}),
													children: [
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "15",
															children: "15분마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "30",
															children: "30분마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "60",
															children: "1시간마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "180",
															children: "3시간마다"
														})
													]
												})]
											}),
											/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "automation-inline-switch",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "기사 전문 저장 (무료 공개 본문만, 로컬 보관용)" }), /* @__PURE__ */ (0, K.jsx)(Vu, {
													ariaLabel: "기사 전문 저장",
													checked: c.rss?.saveFullText !== !1,
													onChange: (e) => u({
														...c,
														rss: {
															...c.rss,
															saveFullText: e
														}
													}),
													compact: !0
												})]
											}),
											/* @__PURE__ */ (0, K.jsxs)("label", {
												className: "field",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "보관 기간" }), /* @__PURE__ */ (0, K.jsx)("select", {
													value: String(Ee),
													onChange: (e) => u({
														...c,
														rss: {
															...c.rss,
															retentionDays: Number(e.currentTarget.value)
														}
													}),
													children: td.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
														value: e.value,
														children: e.label
													}, e.value))
												})]
											}),
											/* @__PURE__ */ (0, K.jsx)(od, {
												preview: h,
												days: Ee
											}),
											/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "automation-card-actions",
												children: [/* @__PURE__ */ (0, K.jsx)("button", {
													type: "button",
													className: "btn",
													disabled: G === "retention",
													onClick: De,
													children: G === "retention" ? "정리하는 중…" : "지금 정리"
												}), /* @__PURE__ */ (0, K.jsx)("span", {
													className: "settings-hint",
													children: ad(h?.reclaimableBytes)
												})]
											}),
											/* @__PURE__ */ (0, K.jsx)(ld, { run: xe.rss })
										]
									}),
									/* @__PURE__ */ (0, K.jsxs)("section", {
										className: "automation-card",
										children: [
											/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "automation-card-head",
												children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [
													/* @__PURE__ */ (0, K.jsx)("span", { children: "Market Memory" }),
													/* @__PURE__ */ (0, K.jsx)("strong", { children: "시장 메모리 업데이트" }),
													/* @__PURE__ */ (0, K.jsx)("p", { children: "최근 RSS와 시장 자료를 중기 시장 판단용 컨텍스트로 정리합니다." })
												] }), /* @__PURE__ */ (0, K.jsx)(Vu, {
													ariaLabel: "Market Memory 자동 정리",
													checked: !!c.marketMemory?.enabled,
													onChange: (e) => u({
														...c,
														marketMemory: {
															...c.marketMemory,
															enabled: e
														}
													}),
													compact: !0
												})]
											}),
											/* @__PURE__ */ (0, K.jsxs)("label", {
												className: "field",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "정리 간격" }), /* @__PURE__ */ (0, K.jsxs)("select", {
													value: String(c.marketMemory?.intervalMinutes || 1440),
													onChange: (e) => u({
														...c,
														marketMemory: {
															...c.marketMemory,
															intervalMinutes: e.currentTarget.value
														}
													}),
													children: [
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "720",
															children: "12시간마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "1440",
															children: "하루마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "2880",
															children: "이틀마다"
														}),
														/* @__PURE__ */ (0, K.jsx)("option", {
															value: "10080",
															children: "일주일마다"
														})
													]
												})]
											}),
											/* @__PURE__ */ (0, K.jsxs)("div", {
												className: "automation-inline-switch",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "RSS 수집 직후에도 정리" }), /* @__PURE__ */ (0, K.jsx)(Vu, {
													ariaLabel: "RSS 수집 직후 Market Memory 정리",
													checked: !!c.marketMemory?.runAfterRss,
													onChange: (e) => u({
														...c,
														marketMemory: {
															...c.marketMemory,
															runAfterRss: e
														}
													}),
													compact: !0
												})]
											}),
											/* @__PURE__ */ (0, K.jsx)(ld, { run: xe.marketMemory })
										]
									}),
									/* @__PURE__ */ (0, K.jsxs)("section", {
										className: "automation-card",
										children: [
											/* @__PURE__ */ (0, K.jsx)("div", {
												className: "automation-card-head",
												children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [
													/* @__PURE__ */ (0, K.jsx)("span", { children: "Daily Briefing" }),
													/* @__PURE__ */ (0, K.jsx)("strong", { children: "브리핑 생성" }),
													/* @__PURE__ */ (0, K.jsx)("p", { children: "예약한 시각에 그 시장의 일일 브리핑을 만듭니다. 마감 시각이 시장마다 달라 여러 개를 둘 수 있습니다." })
												] })
											}),
											/* @__PURE__ */ (0, K.jsx)(cd, {
												schedules: c.briefingSchedules || [],
												watched: _,
												runsById: Se,
												onChange: (e) => u({
													...c,
													briefingSchedules: e
												})
											}),
											/* @__PURE__ */ (0, K.jsxs)("label", {
												className: "field",
												children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "시각을 놓쳤을 때" }), /* @__PURE__ */ (0, K.jsx)("select", {
													value: String(c.missedRuns?.catchUpHours ?? 3),
													onChange: (e) => u({
														...c,
														missedRuns: { catchUpHours: e.currentTarget.value }
													}),
													children: $u.map((e) => /* @__PURE__ */ (0, K.jsx)("option", {
														value: e.value,
														children: e.label
													}, e.value))
												})]
											})
										]
									})
								]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "filter-actions settings-actions",
								children: [be && !G && /* @__PURE__ */ (0, K.jsx)("span", {
									className: "settings-dirty-hint",
									children: "저장 안 된 변경"
								}), /* @__PURE__ */ (0, K.jsx)("button", {
									className: be && !G ? "btn btn--primary" : "btn",
									type: "button",
									onClick: Ne,
									disabled: G === "automation",
									children: "자동화 저장"
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "automation"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "input-panel-header",
								children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "캐시 관리" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "기업 분석용 SEC/DART per-company 캐시 중 오래된 항목만 정리합니다. 공통 ticker/corpCode 목록은 삭제하지 않습니다." })] }), /* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									onClick: we,
									disabled: G === "cache",
									children: G === "cache" ? "확인 중" : "상태 확인"
								})]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "cache-summary",
								children: [/* @__PURE__ */ (0, K.jsxs)("section", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "전체 캐시" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: x ? `${x.total_mb || 0} MB` : "상태 미확인" })] }), /* @__PURE__ */ (0, K.jsxs)("section", { children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "정리 대상" }), /* @__PURE__ */ (0, K.jsx)("strong", { children: x ? `${x.stale_mb || 0} MB` : "상태 미확인" })] })]
							}),
							x?.stats?.length ? /* @__PURE__ */ (0, K.jsx)("div", {
								className: "cache-list",
								children: x.stats.map((e) => /* @__PURE__ */ (0, K.jsxs)("div", {
									className: "cache-row",
									children: [
										/* @__PURE__ */ (0, K.jsx)("strong", { children: e.directory }),
										/* @__PURE__ */ (0, K.jsxs)("span", { children: [
											e.files || 0,
											"개 · ",
											e.total_mb || 0,
											"MB"
										] }),
										/* @__PURE__ */ (0, K.jsxs)("small", { children: [
											"오래된 항목 ",
											e.stale_files || 0,
											"개 · 보관 ",
											e.max_age_days || 0,
											"일"
										] })
									]
								}, e.directory || "cache"))
							}) : /* @__PURE__ */ (0, K.jsx)("p", {
								className: "section-subtitle",
								children: "상태 확인을 누르면 캐시 사용량을 확인합니다."
							}),
							/* @__PURE__ */ (0, K.jsx)("div", {
								className: "filter-actions settings-actions",
								children: /* @__PURE__ */ (0, K.jsx)("button", {
									className: "btn",
									type: "button",
									onClick: Te,
									disabled: G === "cache-cleanup",
									children: G === "cache-cleanup" ? "정리 중" : "오래된 캐시 정리"
								})
							}),
							/* @__PURE__ */ (0, K.jsx)(nd, {
								note: ne,
								panel: "cache"
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsxs)("section", {
						className: "settings-panel input-panel",
						children: [/* @__PURE__ */ (0, K.jsx)("div", {
							className: "input-panel-header",
							children: /* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "이전 작업 기록" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "예전 버전이 남긴 작업 기록 파일을 현재 저장소로 한 번만 옮깁니다. 보고서와 제안 파일은 건드리지 않습니다." })] })
						}), /* @__PURE__ */ (0, K.jsx)(Pu, {})]
					})
				]
			})
		]
	});
}
//#endregion
//#region src/app/watchlist/ConsultationEntry.tsx
function hd({ item: e }) {
	return /* @__PURE__ */ (0, K.jsx)("button", {
		type: "button",
		className: "btn btn--primary",
		onClick: () => Bc({
			title: `${e} 대화`,
			scope: {
				kind: "watchlist",
				id: e,
				tickers: [e]
			},
			initialMessage: `${e}에 대해 지금 확인해야 할 변화와 장기 thesis 영향을 함께 검토해줘.`
		}),
		children: "짚어보기"
	});
}
//#endregion
//#region src/app/watchlist/FundamentalsPanel.tsx
function gd(e) {
	let [t, n] = (0, l.useState)(null), [r, i] = (0, l.useState)("");
	return (0, l.useEffect)(() => {
		let t = !0;
		if (n(null), i(""), e) return B(`/api/market/fundamentals?symbol=${encodeURIComponent(e)}`).then((e) => {
			t && n(e);
		}).catch((e) => {
			t && i(e instanceof Error ? e.message : "지표를 불러오지 못했습니다.");
		}), () => {
			t = !1;
		};
	}, [e]), {
		payload: t,
		error: r
	};
}
function _d(e, t = 1) {
	return e == null || !Number.isFinite(e) ? "—" : e.toLocaleString("ko-KR", {
		maximumFractionDigits: t,
		minimumFractionDigits: 0
	});
}
function vd(e) {
	return e == null || !Number.isFinite(e) ? "—" : `${(e * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}
function $(e) {
	return e == null || !Number.isFinite(e) ? "—" : `${e.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
}
function yd(e, t) {
	if (e == null || t == null || !Number.isFinite(e) || !Number.isFinite(t)) return "—";
	let n = Math.max(Math.abs(e), Math.abs(t)) >= 1e3 ? 0 : 2, r = (e) => e.toLocaleString("ko-KR", { maximumFractionDigits: n });
	return `${r(e)} ~ ${r(t)}`;
}
function bd(e) {
	let t = e.currency || "USD";
	return [
		{
			label: "시가총액",
			hint: "주가 × 발행주식수",
			value: Ga(e.marketCap, t)
		},
		{
			label: "PER",
			hint: "주가 ÷ 최근 4분기 EPS",
			value: _d(e.trailingPE)
		},
		{
			label: "선행 PER",
			hint: "주가 ÷ 예상 EPS",
			value: _d(e.forwardPE)
		},
		{
			label: "PBR",
			hint: "주가 ÷ 주당순자산",
			value: _d(e.priceToBook, 2)
		},
		{
			label: "ROE",
			hint: "순이익 ÷ 자기자본",
			value: vd(e.returnOnEquity)
		},
		{
			label: "영업이익률",
			hint: "영업이익 ÷ 매출",
			value: vd(e.operatingMargins)
		},
		{
			label: "순이익률",
			hint: "순이익 ÷ 매출",
			value: vd(e.profitMargins)
		},
		{
			label: "배당수익률",
			hint: "연간 배당 ÷ 주가",
			value: $(e.dividendYield)
		},
		{
			label: "매출 성장",
			hint: "전년 동기 대비",
			value: vd(e.revenueGrowth)
		},
		{
			label: "베타",
			hint: "시장 대비 변동성",
			value: _d(e.beta, 2)
		},
		{
			label: "52주 범위",
			hint: "최근 1년 저가 ~ 고가",
			value: yd(e.fiftyTwoWeekLow, e.fiftyTwoWeekHigh)
		}
	];
}
function xd(e, t) {
	return e == null || !Number.isFinite(e) || t == null || !Number.isFinite(t) || t === 0 ? null : e / t * 100;
}
var Sd = "color-mix(in srgb, var(--folio-ink) 42%, transparent)", Cd = (e) => `color-mix(in srgb, ${e} 45%, transparent)`, wd = [
	{
		key: "earnings",
		label: "이익",
		mode: "bars",
		format: "amount",
		colors: [
			Sd,
			"var(--folio-green)",
			Cd("var(--folio-green)")
		],
		series: [
			{
				key: "revenue",
				label: "매출",
				of: (e) => e.revenue
			},
			{
				key: "operatingIncome",
				label: "영업이익",
				of: (e) => e.operatingIncome
			},
			{
				key: "netIncome",
				label: "순이익",
				of: (e) => e.netIncome
			}
		]
	},
	{
		key: "balance",
		label: "재무",
		mode: "bars",
		format: "amount",
		colors: [
			Sd,
			"var(--folio-chart-1)",
			Cd("var(--folio-chart-1)")
		],
		series: [
			{
				key: "currentAssets",
				label: "유동자산",
				of: (e) => e.currentAssets
			},
			{
				key: "currentLiabilities",
				label: "유동부채",
				of: (e) => e.currentLiabilities
			},
			{
				key: "nonCurrentLiabilities",
				label: "비유동부채",
				of: (e) => e.nonCurrentLiabilities
			}
		]
	},
	{
		key: "stability",
		label: "안정성",
		mode: "lines",
		format: "percent",
		colors: ["var(--folio-green)", "var(--folio-burgundy)"],
		series: [{
			key: "currentRatio",
			label: "유동비율",
			of: (e) => xd(e.currentAssets, e.currentLiabilities)
		}, {
			key: "debtRatio",
			label: "부채비율",
			of: (e) => xd(e.totalDebt, e.stockholdersEquity)
		}]
	},
	{
		key: "cashflow",
		label: "현금흐름",
		mode: "bars",
		format: "amount",
		colors: [
			Sd,
			"var(--folio-gold)",
			Cd("var(--folio-gold)")
		],
		series: [
			{
				key: "operatingCashFlow",
				label: "영업현금흐름",
				of: (e) => e.operatingCashFlow
			},
			{
				key: "freeCashFlow",
				label: "잉여현금흐름",
				of: (e) => e.freeCashFlow
			},
			{
				key: "capitalExpenditure",
				label: "설비투자",
				of: (e) => e.capitalExpenditure
			}
		]
	}
];
function Td(e) {
	let t = String(e || "");
	return /^\d{4}-\d{2}/.test(t) ? `${t.slice(2, 4)}년 ${Number(t.slice(5, 7))}월` : "";
}
function Ed(e, t) {
	let n = e.filter((e) => e !== null && Number.isFinite(e));
	if (!n.length) return {
		max: 0,
		min: 0
	};
	let r = Math.max(...n), i = Math.min(...n);
	if (t === "bars") r = Math.max(r, 0), i = Math.min(i, 0);
	else {
		let e = (r - i || Math.abs(r) || 1) * .15;
		r += e, i -= e;
	}
	return {
		max: r,
		min: i
	};
}
function Dd({ quarters: e, currency: t }) {
	let [n, r] = (0, l.useState)(wd[0].key), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(null), c = wd.find((e) => e.key === n) || wd[0], u = (e || []).filter((e) => c.series.some((t) => t.of(e) != null)), d = Math.max(0, u.length - 1), f = Math.min(i ?? d, d), p = f - 1, m = c.series.map((e) => u.map((t) => {
		let n = e.of(t);
		return n == null || !Number.isFinite(n) ? null : n;
	})), h = Ed(m.flat(), c.mode), g = h.max - h.min, _ = u.length ? 560 / u.length : 560, v = Math.min(30, (_ - 20) / c.series.length), y = g > 0 ? h.max / g * 190 : 190, b = (e) => (h.max - e) / g * 190, x = (e) => e * _ + _ / 2, S = (e) => c.format === "percent" ? $(e) : Ga(e, t), C = (e, t) => {
		if (e === null || t === null) return {
			text: "—",
			tone: "flat"
		};
		if (c.format === "percent") {
			let n = e - t;
			return {
				text: `${n > 0 ? "+" : ""}${n.toFixed(1)}%p`,
				tone: Ya(n / 100)
			};
		}
		let n = qa(e, t);
		return {
			text: n === null ? "—" : Ja(n),
			tone: Ya(n)
		};
	}, w = (e) => {
		r(e), a(null), s(null);
	}, T = /* @__PURE__ */ (0, K.jsx)("div", {
		className: "segment",
		role: "group",
		"aria-label": "분기 차트 종류",
		children: wd.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
			type: "button",
			"aria-pressed": e.key === n,
			onClick: () => w(e.key),
			children: e.label
		}, e.key))
	});
	return u.length < 2 || g <= 0 ? /* @__PURE__ */ (0, K.jsxs)("figure", {
		className: "watchlist-quarterly",
		children: [T, /* @__PURE__ */ (0, K.jsxs)("p", {
			className: "section-subtitle",
			children: [
				"이 종목은 ",
				c.label,
				" 분기 자료를 받지 못했습니다."
			]
		})]
	}) : /* @__PURE__ */ (0, K.jsxs)("figure", {
		className: "watchlist-quarterly",
		children: [
			T,
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-quarterly__plot",
				onMouseLeave: () => s(null),
				children: [/* @__PURE__ */ (0, K.jsxs)("svg", {
					viewBox: "0 0 560 214",
					role: "img",
					"aria-label": `최근 ${u.length}개 분기 ${c.series.map((e) => e.label).join("·")}.`,
					children: [
						[
							.25,
							.5,
							.75
						].map((e) => /* @__PURE__ */ (0, K.jsx)("line", {
							x1: 0,
							x2: 560,
							y1: 190 * e,
							y2: 190 * e,
							className: "watchlist-quarterly__grid"
						}, e)),
						c.mode === "bars" && /* @__PURE__ */ (0, K.jsx)("line", {
							x1: 0,
							x2: 560,
							y1: y,
							y2: y,
							className: "watchlist-quarterly__baseline"
						}),
						u.map((e, t) => /* @__PURE__ */ (0, K.jsx)("text", {
							x: x(t),
							y: 207,
							textAnchor: "middle",
							className: "watchlist-quarterly__axis",
							children: Td(e.quarter)
						}, e.quarter || t)),
						c.mode === "bars" && u.map((e, t) => {
							let n = t * _ + (_ - v * c.series.length - 10) / 2;
							return /* @__PURE__ */ (0, K.jsx)("g", { children: c.series.map((e, r) => {
								let i = m[r][t];
								if (i === null) return null;
								let a = Math.min(b(i), y), o = Math.max(2, Math.abs(b(i) - y));
								return /* @__PURE__ */ (0, K.jsx)("rect", {
									className: "watchlist-quarterly__bar",
									fill: c.colors[r % c.colors.length],
									opacity: t === f ? 1 : .75,
									x: n + r * (v + 5),
									y: a,
									width: v,
									height: o,
									rx: 4
								}, e.key);
							}) }, e.quarter || t);
						}),
						c.mode === "lines" && c.series.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("g", { children: [/* @__PURE__ */ (0, K.jsx)("polyline", {
							className: "watchlist-quarterly__line",
							stroke: c.colors[t % c.colors.length],
							points: m[t].map((e, t) => e === null ? null : `${x(t).toFixed(1)},${b(e).toFixed(1)}`).filter(Boolean).join(" ")
						}), m[t].map((e, n) => e === null ? null : /* @__PURE__ */ (0, K.jsx)("circle", {
							cx: x(n),
							cy: b(e),
							r: n === f ? 4.5 : 3,
							fill: c.colors[t % c.colors.length]
						}, n))] }, e.key)),
						u.map((e, t) => /* @__PURE__ */ (0, K.jsx)("rect", {
							className: "watchlist-quarterly__hit",
							x: t * _,
							y: 0,
							width: _,
							height: 214,
							tabIndex: 0,
							role: "button",
							"aria-label": `${Td(e.quarter)} 수치 보기`,
							onMouseEnter: () => {
								a(t), s((t + .5) / u.length);
							},
							onFocus: () => {
								a(t), s((t + .5) / u.length);
							}
						}, `hit-${e.quarter || t}`))
					]
				}), o !== null && /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "analysis-chart-hover",
					"data-side": o > .5 ? "left" : "right",
					style: o > .5 ? { right: `${(1 - o) * 100}%` } : { left: `${o * 100}%` },
					children: [/* @__PURE__ */ (0, K.jsx)("b", { children: Td(u[f]?.quarter) }), c.series.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("p", { children: [
						/* @__PURE__ */ (0, K.jsx)("span", {
							className: "analysis-chart-swatch",
							style: { background: c.colors[t % c.colors.length] }
						}),
						/* @__PURE__ */ (0, K.jsx)("span", { children: e.label }),
						/* @__PURE__ */ (0, K.jsx)("em", { children: S(m[t][f]) })
					] }, e.key))]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "analysis-chart-readout",
				children: [/* @__PURE__ */ (0, K.jsxs)("p", {
					className: "analysis-chart-readout-head",
					children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: Td(u[f]?.quarter) }), p >= 0 && /* @__PURE__ */ (0, K.jsxs)("span", { children: [Td(u[p]?.quarter), " 대비"] })]
				}), c.series.map((e, t) => {
					let n = m[t][f], r = p >= 0 ? m[t][p] : null, i = C(n, r);
					return /* @__PURE__ */ (0, K.jsxs)("p", {
						className: "analysis-chart-readout-row",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "analysis-chart-swatch",
								style: { background: c.colors[t % c.colors.length] }
							}),
							/* @__PURE__ */ (0, K.jsx)("span", { children: e.label }),
							/* @__PURE__ */ (0, K.jsx)("b", { children: S(n) }),
							/* @__PURE__ */ (0, K.jsx)("em", {
								"data-direction": i.tone,
								children: i.text
							})
						]
					}, e.key);
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "watchlist-quarterly__table-wrap",
				children: /* @__PURE__ */ (0, K.jsxs)("table", {
					className: "watchlist-quarterly__table",
					children: [/* @__PURE__ */ (0, K.jsx)("thead", { children: /* @__PURE__ */ (0, K.jsxs)("tr", { children: [/* @__PURE__ */ (0, K.jsx)("th", {
						scope: "col",
						children: "항목"
					}), u.map((e) => /* @__PURE__ */ (0, K.jsx)("th", {
						scope: "col",
						children: Td(e.quarter)
					}, e.quarter))] }) }), /* @__PURE__ */ (0, K.jsx)("tbody", { children: c.series.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("tr", { children: [/* @__PURE__ */ (0, K.jsxs)("th", {
						scope: "row",
						children: [/* @__PURE__ */ (0, K.jsx)("i", {
							className: "watchlist-quarterly__dot",
							style: { background: c.colors[t % c.colors.length] },
							"aria-hidden": "true"
						}), e.label]
					}), u.map((e, n) => /* @__PURE__ */ (0, K.jsx)("td", { children: S(m[t][n]) }, e.quarter))] }, e.key)) })]
				})
			})
		]
	});
}
function Od({ payload: e }) {
	let [t, n] = (0, l.useState)(!1), r = String(e.longBusinessSummary || "").trim(), i = [{
		label: "섹터",
		value: e.sector || ""
	}, {
		label: "산업",
		value: e.industry || ""
	}].filter((e) => e.value);
	return !r && !i.length ? null : /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-profile",
		children: [
			r && /* @__PURE__ */ (0, K.jsx)("p", {
				className: t ? "watchlist-profile__summary" : "watchlist-profile__summary watchlist-profile__summary--clamped",
				children: r
			}),
			r && /* @__PURE__ */ (0, K.jsx)("button", {
				type: "button",
				className: "btn btn--text watchlist-profile__more",
				"aria-expanded": t,
				onClick: () => n((e) => !e),
				children: t ? "접기" : "더보기"
			}),
			i.map((e) => /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-fundamentals-row",
				children: [/* @__PURE__ */ (0, K.jsx)("dt", { children: e.label }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e.value })]
			}, e.label))
		]
	});
}
function kd({ ticker: e, payload: t, error: n }) {
	if (!e) return null;
	if (n) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "section-subtitle",
		children: n
	});
	if (!t) return /* @__PURE__ */ (0, K.jsx)("p", {
		className: "section-subtitle watchlist-fundamentals-skeleton",
		children: "지표를 불러오는 중입니다."
	});
	let r = t.currency || "USD";
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "watchlist-fundamentals",
		children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [/* @__PURE__ */ (0, K.jsx)(Od, { payload: t }), /* @__PURE__ */ (0, K.jsx)("dl", {
			className: "watchlist-fundamentals-rows",
			children: bd(t).map((e) => /* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-fundamentals-row",
				children: [/* @__PURE__ */ (0, K.jsxs)("dt", { children: [e.label, /* @__PURE__ */ (0, K.jsx)("small", { children: e.hint })] }), /* @__PURE__ */ (0, K.jsx)("dd", { children: e.value })]
			}, e.label))
		})] }), /* @__PURE__ */ (0, K.jsx)(Dd, {
			quarters: t.quarters || [],
			currency: r
		})]
	});
}
//#endregion
//#region src/app/WatchlistRoute.tsx
function Ad(e) {
	let t = /* @__PURE__ */ new Set();
	return e.map((e) => String(e || "").trim()).filter(Boolean).filter((e) => {
		let n = e.toLowerCase();
		return !t.has(n) && (t.add(n), !0);
	});
}
function jd(e) {
	return e.ticker || e.item || "";
}
function Md(e) {
	return e.companyName || e.name || e.item || jd(e);
}
function Nd(e, t = "") {
	return e?.company?.name || e?.item || t || "상세 보기";
}
function Pd(e) {
	if (!e) return "상세 정보를 불러오는 중입니다.";
	let t = e.company || {};
	return [
		t.ticker || "",
		t.market || "",
		e.newsCount ? `${e.newsCount}개 뉴스` : ""
	].filter(Boolean).join(" · ") || "확인된 심볼 정보가 없습니다.";
}
function Fd(e = []) {
	return [...e].sort((e, t) => String(t.date || "").localeCompare(String(e.date || "")));
}
function Id(e) {
	return e.title || e.url || e.path || "자료";
}
function Ld(e) {
	return [e.source, e.date].filter(Boolean).join(" · ");
}
var Rd = /^(?:co|inc|ltd|corp|llc|plc|ag|nv|sa|se|kk|gmbh|s\.?a\.?s|co\.?,?\s*ltd)\.?$/i;
function zd(e, t) {
	let n = String(e || "").trim();
	return n ? t ? [n] : n.split(/[,;\n]/).map((e) => e.trim()).filter(Boolean).filter((e) => !Rd.test(e)) : [];
}
function Bd(e) {
	window.location.hash = e ? `#/watchlist/${encodeURIComponent(e)}` : "#/watchlist";
}
function Vd() {
	let e = window.location.hash.match(/^#\/?watchlist\/(.+)$/);
	return e ? decodeURIComponent(e[1]) : "";
}
function Hd() {
	return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "watchlist";
}
function Ud() {
	let [e, t] = (0, l.useState)([]), [n, r] = (0, l.useState)([]), [i, a] = (0, l.useState)(""), [o, s] = (0, l.useState)(() => Vd()), [c, u] = (0, l.useState)(null), [d, f] = (0, l.useState)(!1), [p, m] = (0, l.useState)(!1), [h, g] = (0, l.useState)(!1), [_, v] = (0, l.useState)(""), [y, b] = (0, l.useState)(""), [x, S] = (0, l.useState)({}), [C, w] = (0, l.useState)("3m"), [T, E] = (0, l.useState)("line"), D = (0, l.useCallback)(async (e) => {
		if (!e.length) {
			r([]);
			return;
		}
		let t = await B("/api/watchlist/overview"), n = Array.isArray(t.items) ? t.items : [];
		r(n), Ba(n.map((e) => e.ticker || "").filter(Boolean)).then(S);
	}, []), O = (0, l.useCallback)(async () => {
		f(!0), v("");
		try {
			let e = await B("/api/watchlist"), n = Ad(Array.isArray(e) ? e : []);
			t(n), await D(n), Qe("watchlist", {
				surface: "watchlist",
				viewId: "watchlist",
				reportKind: "",
				reportId: ""
			});
		} catch (e) {
			v(e instanceof Error ? e.message : "워치리스트를 불러오지 못했습니다.");
		} finally {
			f(!1);
		}
	}, [D]);
	(0, l.useEffect)(() => {
		O();
	}, [O]), (0, l.useEffect)(() => {
		let e = () => {
			Hd() && s(Vd());
		};
		return window.addEventListener("hashchange", e), e(), () => window.removeEventListener("hashchange", e);
	}, []), (0, l.useEffect)(() => {
		let e = !0;
		async function t(t) {
			m(!0), v(""), u({ item: t }), Qe("watchlist", {
				surface: "watchlist_detail",
				viewId: "watchlist",
				reportKind: "watchlist",
				reportId: t,
				marketScope: ""
			});
			try {
				let n = await B(`/api/watchlist/detail?item=${encodeURIComponent(t)}&limit=12`);
				if (!e) return;
				u(n);
			} catch (t) {
				if (!e) return;
				v(t instanceof Error ? t.message : "상세 정보를 불러오지 못했습니다.");
			} finally {
				e && m(!1);
			}
		}
		return o ? t(o) : (u(null), Qe("watchlist", {
			surface: "watchlist",
			viewId: "watchlist",
			reportKind: "",
			reportId: ""
		})), () => {
			e = !1;
		};
	}, [o]);
	async function k(e, n) {
		g(!0), v("");
		try {
			let r = await V("/api/watchlist", { items: e }), i = Ad(Array.isArray(r) ? r : []);
			t(i), await D(i), n && b(n);
		} catch (e) {
			v(e instanceof Error ? e.message : "워치리스트 저장에 실패했습니다.");
		} finally {
			g(!1);
		}
	}
	let { resolution: A, pending: j, picked: M, pick: N } = ra(i, { preferHome: !0 }), P = !!M || A?.status === "confident", F = i.trim() ? M ? `${M.name}로 추가합니다.` : j ? "확인 중…" : A?.status === "confident" && A.match ? `${A.match.name}로 추가합니다.` : A?.status === "ambiguous" && A.candidates.some((e) => e.strong) ? "여러 기업이 맞습니다. 고르거나, 이대로 주제 키워드로 추가합니다." : "주제 키워드로 추가합니다." : "종목은 이름이나 티커로, 관심 주제는 그대로 적으면 됩니다.";
	async function I(e) {
		try {
			return (await B(`/api/watchlist/resolve?keyword=${encodeURIComponent(e)}`)).keyword || e;
		} catch {
			return e;
		}
	}
	async function L() {
		let t = zd(i, P);
		if (!t.length) return;
		let n = [...e];
		for (let e of t) {
			let t = await I(e);
			t && !n.some((e) => e.toLowerCase() === t.toLowerCase()) && n.push(t);
		}
		a(""), n.length !== e.length && await k(n, "워치리스트에 추가했습니다.");
	}
	async function R(t) {
		await k(e.filter((e) => e !== t), "워치리스트에서 삭제했습니다."), o === t && Bd();
	}
	let z = (0, l.useMemo)(() => Fd(c?.news || []), [c]), H = /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("div", {
		className: "watchlist-detail-section__head",
		children: /* @__PURE__ */ (0, K.jsx)("h3", { children: "수집한 뉴스" })
	}), p ? /* @__PURE__ */ (0, K.jsx)("p", {
		className: "section-subtitle",
		children: "관련 뉴스를 불러오는 중입니다."
	}) : z.length ? /* @__PURE__ */ (0, K.jsx)("div", {
		className: "watchlist-detail-news-list",
		children: z.map((e, t) => /* @__PURE__ */ (0, K.jsxs)("article", {
			className: "watchlist-news-row",
			children: [
				/* @__PURE__ */ (0, K.jsx)("span", {
					className: "watchlist-news-row__meta",
					children: Ld(e)
				}),
				/* @__PURE__ */ (0, K.jsx)("h4", { children: e.url ? /* @__PURE__ */ (0, K.jsx)("a", {
					href: e.url,
					target: "_blank",
					rel: "noopener noreferrer",
					children: Id(e)
				}) : /* @__PURE__ */ (0, K.jsx)("span", { children: Id(e) }) }),
				e.snippet && /* @__PURE__ */ (0, K.jsx)("p", { children: e.snippet })
			]
		}, `${Id(e)}-${t}`))
	}) : /* @__PURE__ */ (0, K.jsx)("p", {
		className: "section-subtitle",
		children: "수집된 관련 뉴스가 없습니다."
	})] }), U = Nd(c, o), ee = n.find((e) => (e.item || Md(e)) === o) || null, te = String(ee?.ticker || c?.company?.ticker || "").trim(), W = ee ? Md(ee) : Nd(c, o), G = gd(te);
	function q(e) {
		let t = String(e?.ticker || "").toUpperCase();
		return t ? x[t] : void 0;
	}
	return o ? /* @__PURE__ */ (0, K.jsx)("div", {
		className: "react-watchlist-route",
		"data-watchlist-route": !0,
		children: /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "watchlist-detail-inline",
			children: [/* @__PURE__ */ (0, K.jsxs)("nav", {
				className: "reader-breadcrumb",
				"aria-label": "현재 위치",
				children: [
					/* @__PURE__ */ (0, K.jsx)("button", {
						type: "button",
						className: "reader-crumb-link",
						onClick: () => Bd(),
						children: "워치리스트"
					}),
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "reader-breadcrumb-sep",
						"aria-hidden": "true",
						children: "›"
					}),
					/* @__PURE__ */ (0, K.jsx)("span", {
						className: "reader-breadcrumb-leaf",
						children: U
					})
				]
			}), /* @__PURE__ */ (0, K.jsxs)("section", {
				className: "watchlist-detail-dialog",
				role: "region",
				"aria-labelledby": "watchlistDetailTitle",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "watchlist-detail-head",
						children: [/* @__PURE__ */ (0, K.jsxs)("div", { children: [
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "section-kicker",
								children: "WATCHLIST"
							}),
							/* @__PURE__ */ (0, K.jsx)("h2", {
								id: "watchlistDetailTitle",
								children: U
							}),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "section-subtitle",
								children: Pd(c)
							})
						] }), /* @__PURE__ */ (0, K.jsxs)("div", {
							className: "watchlist-detail-actions",
							children: [/* @__PURE__ */ (0, K.jsx)(hd, { item: o }), /* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn btn--icon",
								type: "button",
								"aria-label": "닫기",
								"data-tooltip": "닫기",
								"data-tooltip-pos": "left",
								onClick: () => Bd(),
								children: "×"
							})]
						})]
					}),
					_ && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "react-dashboard-error",
						children: _
					}),
					te ? /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "watchlist-detail-grid",
						children: [
							/* @__PURE__ */ (0, K.jsxs)("section", {
								className: "watchlist-detail-section watchlist-detail-section--metrics",
								children: [/* @__PURE__ */ (0, K.jsx)("div", {
									className: "watchlist-detail-section__head",
									children: /* @__PURE__ */ (0, K.jsx)("h3", { children: "재무·투자 지표" })
								}), /* @__PURE__ */ (0, K.jsx)(kd, {
									ticker: te,
									payload: G.payload,
									error: G.error
								})]
							}),
							/* @__PURE__ */ (0, K.jsx)("section", {
								className: "watchlist-detail-section watchlist-detail-section--chart",
								children: /* @__PURE__ */ (0, K.jsx)(Qo, {
									symbol: te,
									label: W || te,
									range: C,
									style: T,
									onRange: w,
									onStyle: E,
									showEvent: !1
								})
							}),
							/* @__PURE__ */ (0, K.jsx)("section", {
								className: "watchlist-detail-section watchlist-detail-section--earnings",
								children: /* @__PURE__ */ (0, K.jsx)(Qa, { ticker: te })
							}),
							/* @__PURE__ */ (0, K.jsx)("section", {
								className: "watchlist-detail-section watchlist-detail-section--news",
								children: H
							})
						]
					}) : /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("p", {
						className: "section-subtitle",
						children: "이 항목은 종목 코드가 없어 차트와 실적을 표시하지 않습니다."
					}), /* @__PURE__ */ (0, K.jsx)("section", {
						className: "watchlist-detail-section",
						children: H
					})] }),
					te && /* @__PURE__ */ (0, K.jsx)("p", {
						className: "watchlist-detail-source",
						children: "출처 yfinance — 기업분석(SEC 공시 기준)과 수치가 다를 수 있습니다."
					})
				]
			})]
		})
	}) : /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "react-watchlist-route",
		"data-watchlist-route": !0,
		children: [
			/* @__PURE__ */ (0, K.jsx)(Xn, {
				eyebrow: "Watchlist",
				title: "워치리스트",
				description: "관심 기업, 섹터, 테마를 추적하고 관련 뉴스와 시장 반응을 확인합니다.",
				actions: /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "brief-controls",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: O,
						disabled: d,
						children: d ? "불러오는 중" : "다시 읽기"
					}), /* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn btn--primary",
						type: "button",
						onClick: () => k(e, "워치리스트를 저장했습니다."),
						disabled: h,
						children: h ? "저장 중" : "저장"
					})]
				})
			}),
			/* @__PURE__ */ (0, K.jsxs)("div", {
				className: "watchlist-editor input-panel",
				children: [
					/* @__PURE__ */ (0, K.jsxs)("div", {
						className: "input-panel-header",
						children: [/* @__PURE__ */ (0, K.jsx)("h3", { children: "키워드 추가" }), /* @__PURE__ */ (0, K.jsx)("p", { children: "관심 기업, 섹터, 테마를 하나씩 추가해 뉴스와 브리핑 추적 범위를 관리합니다." })]
					}),
					/* @__PURE__ */ (0, K.jsxs)("label", {
						className: "portfolio-ticker-field watchlist-add-field",
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "sr-only",
								children: "추가할 종목 또는 키워드"
							}),
							/* @__PURE__ */ (0, K.jsx)("input", {
								value: i,
								onChange: (e) => a(e.currentTarget.value),
								onKeyDown: (e) => {
									e.key === "Enter" && (e.preventDefault(), L());
								},
								placeholder: "예: NVDA, 삼성전자, AI",
								"aria-describedby": "watchlist-resolution",
								autoComplete: "off"
							}),
							A?.status === "ambiguous" && A.candidates.some((e) => e.strong) && !M && /* @__PURE__ */ (0, K.jsx)("div", {
								className: "ticker-suggest",
								role: "listbox",
								"aria-label": "후보 기업",
								children: A.candidates.map((e) => /* @__PURE__ */ (0, K.jsxs)("button", {
									type: "button",
									role: "option",
									"aria-selected": !1,
									onClick: () => {
										N(e, e.name), a(e.name);
									},
									children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: e.ticker }), /* @__PURE__ */ (0, K.jsx)("span", { children: e.name })]
								}, `${e.market}:${e.ticker}`))
							})
						]
					}),
					/* @__PURE__ */ (0, K.jsx)("button", {
						className: "btn",
						type: "button",
						onClick: L,
						disabled: h,
						children: "추가"
					})
				]
			}),
			/* @__PURE__ */ (0, K.jsx)("p", {
				className: "analysis-resolution",
				id: "watchlist-resolution",
				"data-status": i.trim() ? M ? "picked" : A?.status || "idle" : "idle",
				children: F
			}),
			_ && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-error",
				children: _
			}),
			y && /* @__PURE__ */ (0, K.jsx)("p", {
				className: "react-dashboard-warning",
				children: y
			}),
			/* @__PURE__ */ (0, K.jsx)("div", {
				className: "watchlist-grid",
				children: n.length ? n.map((e) => {
					let t = e.item || Md(e);
					return /* @__PURE__ */ (0, K.jsxs)("article", {
						className: "watchlist-card",
						"data-watchlist-detail-item": t,
						tabIndex: 0,
						role: "button",
						"aria-label": `${t} 상세 보기`,
						onClick: () => Bd(t),
						onKeyDown: (e) => {
							(e.key === "Enter" || e.key === " ") && (e.preventDefault(), Bd(t));
						},
						children: [
							/* @__PURE__ */ (0, K.jsx)("span", {
								className: "watchlist-card-accent",
								"aria-hidden": "true"
							}),
							/* @__PURE__ */ (0, K.jsx)("button", {
								className: "btn btn--icon watchlist-card-delete",
								type: "button",
								"aria-label": `${t} 워치리스트에서 삭제`,
								"data-tooltip": "삭제",
								"data-tooltip-pos": "bottom",
								onClick: (e) => {
									e.stopPropagation(), R(t);
								},
								children: /* @__PURE__ */ (0, K.jsx)("svg", {
									width: "13",
									height: "13",
									viewBox: "0 0 16 16",
									fill: "none",
									stroke: "currentColor",
									strokeWidth: "1.4",
									strokeLinecap: "round",
									strokeLinejoin: "round",
									"aria-hidden": "true",
									children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" })
								})
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "watchlist-card-top",
								children: [/* @__PURE__ */ (0, K.jsx)("strong", {
									className: "watchlist-ticker",
									children: jd(e)
								}), /* @__PURE__ */ (0, K.jsx)("h3", { children: Md(e) })]
							}),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "watchlist-card-meta",
								children: [
									e.tags?.length ? /* @__PURE__ */ (0, K.jsx)("div", {
										className: "tags",
										children: e.tags.slice(0, 5).map((e) => /* @__PURE__ */ (0, K.jsx)("span", {
											className: "tag",
											children: e
										}, e))
									}) : null,
									(() => {
										let t = q(e);
										if (!t?.startsAt) return null;
										let n = Ia(t.startsAt);
										return n ? /* @__PURE__ */ (0, K.jsxs)("span", {
											className: "chip watchlist-earnings-chip",
											"data-estimated": Pa(t) ? "true" : void 0,
											title: `실적 ${La(t.startsAt)}${Pa(t) ? " (예정치)" : ""}`,
											children: [
												"실적 ",
												n,
												Pa(t) ? "*" : ""
											]
										}) : null;
									})(),
									/* @__PURE__ */ (0, K.jsxs)("span", {
										className: "watchlist-news-count",
										children: [e.count || 0, "건"]
									})
								]
							})
						]
					}, t);
				}) : /* @__PURE__ */ (0, K.jsx)("div", {
					className: "result",
					children: /* @__PURE__ */ (0, K.jsx)("p", { children: "워치리스트 항목을 저장하면 항목별 최신 뉴스 카드가 표시됩니다." })
				})
			})
		]
	});
}
//#endregion
//#region src/app/AppShell.tsx
var Wd = [
	"light",
	"dark",
	"system"
], Gd = {
	light: "라이트",
	dark: "다크",
	system: "시스템"
};
function Kd({ preference: e }) {
	return e === "light" ? /* @__PURE__ */ (0, K.jsxs)("svg", {
		viewBox: "0 0 16 16",
		fill: "none",
		"aria-hidden": "true",
		children: [/* @__PURE__ */ (0, K.jsx)("circle", {
			cx: "8",
			cy: "8",
			r: "3.1",
			stroke: "currentColor",
			strokeWidth: "1.4"
		}), /* @__PURE__ */ (0, K.jsx)("path", {
			d: "M8 1.4v1.6M8 13v1.6M14.6 8H13M3 8H1.4M12.66 3.34l-1.13 1.13M4.47 11.53l-1.13 1.13M12.66 12.66l-1.13-1.13M4.47 4.47 3.34 3.34",
			stroke: "currentColor",
			strokeWidth: "1.4",
			strokeLinecap: "round"
		})]
	}) : e === "dark" ? /* @__PURE__ */ (0, K.jsx)("svg", {
		viewBox: "0 0 16 16",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", {
			d: "M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8Z",
			stroke: "currentColor",
			strokeWidth: "1.4",
			strokeLinejoin: "round"
		})
	}) : /* @__PURE__ */ (0, K.jsxs)("svg", {
		viewBox: "0 0 16 16",
		fill: "none",
		"aria-hidden": "true",
		children: [/* @__PURE__ */ (0, K.jsx)("rect", {
			x: "1.8",
			y: "2.6",
			width: "12.4",
			height: "8.6",
			rx: "1.4",
			stroke: "currentColor",
			strokeWidth: "1.4"
		}), /* @__PURE__ */ (0, K.jsx)("path", {
			d: "M5.6 13.9h4.8",
			stroke: "currentColor",
			strokeWidth: "1.4",
			strokeLinecap: "round"
		})]
	});
}
function qd() {
	let e = ju(), [t, n] = (0, l.useState)(!1), r = (0, l.useRef)(null), i = (0, l.useRef)(null), a = (0, l.useRef)([]), o = e.preference === "system" ? `시스템 (${Gd[e.resolved]})` : Gd[e.preference];
	(0, l.useEffect)(() => {
		if (!t) return;
		let e = (e) => {
			r.current?.contains(e.target) || n(!1);
		}, a = (e) => {
			e.key === "Escape" && (e.stopPropagation(), n(!1), i.current?.focus());
		};
		return document.addEventListener("pointerdown", e), document.addEventListener("keydown", a, !0), () => {
			document.removeEventListener("pointerdown", e), document.removeEventListener("keydown", a, !0);
		};
	}, [t]), (0, l.useEffect)(() => {
		if (!t) return;
		let n = Math.max(0, Wd.indexOf(e.preference));
		a.current[n]?.focus();
	}, [t, e.preference]);
	let s = (e, t) => {
		let n = (e + t + Wd.length) % Wd.length;
		a.current[n]?.focus();
	};
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "theme-menu",
		ref: r,
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "btn btn--icon",
			type: "button",
			ref: i,
			"aria-haspopup": "menu",
			"aria-expanded": t,
			"aria-label": `화면 테마: ${o}`,
			"data-tooltip": t ? "" : `테마: ${o}`,
			"data-tooltip-pos": "bottom",
			onClick: () => n((e) => !e),
			children: /* @__PURE__ */ (0, K.jsx)(Kd, { preference: e.preference })
		}), t && /* @__PURE__ */ (0, K.jsx)("div", {
			className: "theme-menu-list",
			role: "menu",
			"aria-label": "화면 테마",
			children: Wd.map((t, r) => /* @__PURE__ */ (0, K.jsxs)("button", {
				type: "button",
				role: "menuitemradio",
				"aria-checked": e.preference === t,
				ref: (e) => {
					a.current[r] = e;
				},
				onClick: () => {
					e.setPreference(t), n(!1), i.current?.focus();
				},
				onKeyDown: (e) => {
					e.key === "ArrowDown" && (e.preventDefault(), s(r, 1)), e.key === "ArrowUp" && (e.preventDefault(), s(r, -1));
				},
				children: [/* @__PURE__ */ (0, K.jsx)(Kd, { preference: t }), Gd[t]]
			}, t))
		})]
	});
}
var Jd = [
	"codex",
	"claude",
	"antigravity"
];
function Yd(e) {
	return e ? e.bridgeSupported === !1 ? "지원 안 됨" : e.installed ? e.available ? "사용 가능" : "로그인 필요" : "미설치" : "확인 중";
}
function Xd() {
	let [e, t] = (0, l.useState)(null), [n, r] = (0, l.useState)(!1), [i, a] = (0, l.useState)(!1), o = (0, l.useRef)(null), s = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		let e = !0;
		(async () => {
			try {
				let n = await B("/api/agent-bridge/settings");
				e && t(n);
			} catch {
				e && t(null);
			}
		})();
		let n = (e) => t(e.detail);
		return window.addEventListener("folio:agent-settings-updated", n), () => {
			e = !1, window.removeEventListener("folio:agent-settings-updated", n);
		};
	}, []), (0, l.useEffect)(() => {
		if (!n) return;
		let e = (e) => {
			o.current?.contains(e.target) || r(!1);
		}, t = (e) => {
			e.key === "Escape" && (r(!1), s.current?.focus());
		};
		return document.addEventListener("pointerdown", e), document.addEventListener("keydown", t, !0), () => {
			document.removeEventListener("pointerdown", e), document.removeEventListener("keydown", t, !0);
		};
	}, [n]);
	let c = Jd.map((t) => ({
		id: t,
		row: e?.adapters?.find((e) => e.id === t)
	})), u = e?.provider && Jd.includes(e.provider) ? e.provider : "", d = c.find((e) => e.id === u)?.row?.label || "선택 안 됨";
	async function f(n) {
		a(!0);
		try {
			let r = await V("/api/agent-bridge/settings", {
				provider: n,
				models: Object.fromEntries((e?.adapters || []).map((e) => [e.id, e.model || ""]))
			});
			t(r), window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: r }));
		} catch {} finally {
			a(!1), r(!1), s.current?.focus();
		}
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "theme-menu",
		ref: o,
		children: [/* @__PURE__ */ (0, K.jsx)("button", {
			className: "btn btn--icon",
			type: "button",
			ref: s,
			"aria-haspopup": "menu",
			"aria-expanded": n,
			"aria-label": `Agent CLI: ${d}`,
			"data-tooltip": n ? "" : `Agent CLI: ${d}`,
			"data-tooltip-pos": "bottom",
			onClick: () => r((e) => !e),
			children: /* @__PURE__ */ (0, K.jsxs)("svg", {
				viewBox: "0 0 16 16",
				fill: "none",
				"aria-hidden": "true",
				width: "16",
				height: "16",
				children: [/* @__PURE__ */ (0, K.jsx)("path", {
					d: "M4 5.5 L6.5 8 L4 10.5",
					stroke: "currentColor",
					strokeWidth: "1.6",
					strokeLinecap: "round",
					strokeLinejoin: "round"
				}), /* @__PURE__ */ (0, K.jsx)("path", {
					d: "M8.5 11 H12",
					stroke: "currentColor",
					strokeWidth: "1.6",
					strokeLinecap: "round"
				})]
			})
		}), n && /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "theme-menu-list agent-provider-menu",
			role: "menu",
			"aria-label": "Agent CLI",
			children: [
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "agent-provider-menu__note",
					children: "전역 기본입니다. 예약 브리핑과 기업분석이 이 CLI로 돕니다."
				}),
				c.map(({ id: e, row: t }) => /* @__PURE__ */ (0, K.jsxs)("button", {
					type: "button",
					role: "menuitemradio",
					"aria-checked": u === e,
					disabled: i || t?.bridgeSupported === !1,
					onClick: () => void f(e),
					children: [/* @__PURE__ */ (0, K.jsx)("span", { children: t?.label || e }), /* @__PURE__ */ (0, K.jsx)("small", { children: Yd(t) })]
				}, e)),
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "agent-provider-menu__note",
					children: "도크에서 고르는 CLI는 그 대화에만 적용되며 이 값을 바꾸지 않습니다."
				})
			]
		})]
	});
}
var Zd = [
	{
		id: "home",
		title: "홈",
		routes: ["home", "dashboard"]
	},
	{
		id: "news",
		title: "뉴스",
		routes: [
			"briefing",
			"market-memory",
			"rss"
		]
	},
	{
		id: "portfolio",
		title: "투자",
		routes: ["watchlist", "portfolio"]
	},
	{
		id: "research",
		title: "리서치",
		routes: ["analysis", "deep-research"]
	},
	{
		id: "system",
		title: "",
		routes: ["settings"]
	}
], Qd = {
	home: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [/* @__PURE__ */ (0, K.jsx)("path", { d: "M3 10.5 12 3l9 7.5" }), /* @__PURE__ */ (0, K.jsx)("path", { d: "M5 9.5V21h5v-6h4v6h5V9.5" })]
	}),
	dashboard: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("rect", {
				x: "3",
				y: "3",
				width: "7",
				height: "8",
				rx: "1.5"
			}),
			/* @__PURE__ */ (0, K.jsx)("rect", {
				x: "14",
				y: "3",
				width: "7",
				height: "5",
				rx: "1.5"
			}),
			/* @__PURE__ */ (0, K.jsx)("rect", {
				x: "14",
				y: "12",
				width: "7",
				height: "9",
				rx: "1.5"
			}),
			/* @__PURE__ */ (0, K.jsx)("rect", {
				x: "3",
				y: "15",
				width: "7",
				height: "6",
				rx: "1.5"
			})
		]
	}),
	briefing: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M4 5h12.5v14H5.5A1.5 1.5 0 0 1 4 17.5z" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M16.5 8H20v9a2 2 0 0 1-2 2h-1.5" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M7.5 9h6" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M7.5 13h6" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M7.5 16.5h3.5" })
		]
	}),
	rss: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("path", {
				fill: "currentColor",
				stroke: "none",
				d: "M8 8H6v7c0 1.1.9 2 2 2h9v-2H8V8z"
			}),
			/* @__PURE__ */ (0, K.jsx)("path", {
				fill: "currentColor",
				stroke: "none",
				d: "M20 3h-8c-1.1 0-2 .9-2 2v6c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 8h-8V7h8v4z"
			}),
			/* @__PURE__ */ (0, K.jsx)("path", {
				fill: "currentColor",
				stroke: "none",
				d: "M4 12H2v7c0 1.1.9 2 2 2h9v-2H4v-7z"
			})
		]
	}),
	"market-memory": /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M22 12h-4l-3 8-6-16-3 8H2" })
	}),
	analysis: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M14 3v6h6" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M8 17v-3" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M12 17v-6" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M16 17v-4" })
		]
	}),
	"deep-research": /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M14 11H8m2 4H8m8-8H8m12 3.5V6.8c0-1.68 0-2.52-.327-3.162a3 3 0 0 0-1.311-1.311C17.72 2 16.88 2 15.2 2H8.8c-1.68 0-2.52 0-3.162.327a3 3 0 0 0-1.311 1.311C4 4.28 4 5.12 4 6.8v10.4c0 1.68 0 2.52.327 3.162a3 3 0 0 0 1.311 1.311C6.28 22 7.12 22 8.8 22h2.7M22 22l-1.5-1.5m1-2.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0" })
	}),
	watchlist: /* @__PURE__ */ (0, K.jsx)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M12 13V7m-3 3h6m4 11V7.8c0-1.68 0-2.52-.327-3.162a3 3 0 0 0-1.311-1.311C16.72 3 15.88 3 14.2 3H9.8c-1.68 0-2.52 0-3.162.327a3 3 0 0 0-1.311 1.311C5 5.28 5 6.12 5 7.8V21l7-4z" })
	}),
	portfolio: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M3 7.5h18v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M8 7.5V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2.5" }),
			/* @__PURE__ */ (0, K.jsx)("path", { d: "M3 12h18M10 12v2h4v-2" })
		]
	}),
	settings: /* @__PURE__ */ (0, K.jsxs)("svg", {
		className: "react-left-nav-svg",
		viewBox: "0 0 24 24",
		fill: "none",
		"aria-hidden": "true",
		children: [/* @__PURE__ */ (0, K.jsx)("path", { d: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" }), /* @__PURE__ */ (0, K.jsx)("path", { d: "M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-.4-1.1 1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.1-.4 1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06A2 2 0 1 1 7.22 3.43l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 .4 1.1 1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.2.34.4.7.6 1a1.7 1.7 0 0 0 1.1.4H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.1.4c-.17.14-.31.28-.41.2Z" })]
	})
}, $d = "(max-width: 1024px)";
function ef() {
	return typeof window < "u" && window.matchMedia($d).matches;
}
function tf() {
	let e = window.location.hash || Yi(Eu());
	return /^#\/?office(?:\/|$)/.test(e) ? (window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/home`), Yi("home")) : e;
}
function nf() {
	let [e, t] = (0, l.useState)(() => tf());
	return (0, l.useEffect)(() => {
		let e = () => t(tf());
		return window.addEventListener("hashchange", e), e(), () => window.removeEventListener("hashchange", e);
	}, []), {
		hash: e,
		routeId: Ji(e)
	};
}
async function rf(e) {
	await new Promise((e) => window.setTimeout(e, 1500));
	let t = Date.now() + 6e4;
	for (; Date.now() < t;) {
		try {
			if ((await fetch("/api/dashboard", { cache: "no-store" })).ok) {
				e("재시작 완료 · 새로고침 중"), window.location.reload();
				return;
			}
		} catch {}
		await new Promise((e) => window.setTimeout(e, 1e3));
	}
	e("재시작 확인 실패 · 수동 새로고침 필요");
}
function af() {
	let { hash: e, routeId: t } = nf(), n = Xi(t), r = Eu(Du().preferences), [i, a] = (0, l.useState)(() => localStorage.getItem("folio.react.navCollapsed") === "1"), o = (0, l.useRef)(!1), [s, c] = (0, l.useState)(() => {
		let e = localStorage.getItem("folio.react.agentClosed"), t = e === null || e !== "1";
		return t && ef() ? (o.current = !0, !1) : t;
	}), [u, d] = (0, l.useState)(() => /* @__PURE__ */ new Set([t])), [f, p] = (0, l.useState)(() => ({ [t]: tf() })), [m, h] = (0, l.useState)(""), [g, _] = (0, l.useState)(!1), v = (0, l.useRef)(null), y = (0, l.useRef)(t), b = (0, l.useRef)(!1), x = (0, l.useRef)({}), S = n.id !== "home", C = S && s ? " is-agent-open" : " is-agent-closed";
	(0, l.useEffect)(() => {
		tt(n.id, {
			surface: `react_${n.id}`,
			viewId: n.id
		});
	}, [n.id]), (0, l.useEffect)(() => {
		localStorage.setItem("folio.react.navCollapsed", i ? "1" : "0");
	}, [i]), (0, l.useEffect)(() => {
		if (o.current) {
			o.current = !1;
			return;
		}
		localStorage.setItem("folio.react.agentClosed", s ? "0" : "1");
	}, [s]), (0, l.useEffect)(() => {
		let e = window.matchMedia($d), t = (e) => {
			e.matches && c((e) => e && (o.current = !0, !1));
		};
		return e.addEventListener("change", t), () => e.removeEventListener("change", t);
	}, []), (0, l.useEffect)(() => {
		d((e) => {
			if (e.has(t)) return e;
			let n = new Set(e);
			return n.add(t), n;
		});
	}, [t]), (0, l.useEffect)(() => {
		p((n) => n[t] === e ? n : {
			...n,
			[t]: e
		});
	}, [e, t]), (0, l.useEffect)(() => {
		if (!b.current) {
			b.current = !0, y.current = t;
			return;
		}
		let e = v.current, n = y.current;
		e && (x.current[n] = e.scrollTop, window.requestAnimationFrame(() => {
			e.scrollTop = x.current[t] || 0, e.focus({ preventScroll: !0 });
		})), y.current = t;
	}, [t]), (0, l.useEffect)(() => {
		let e = window.FolioBridge ?? {}, t = e.openAgentDock;
		return window.FolioBridge = {
			...e,
			openAgentDock(e = {}) {
				c(!0), window.dispatchEvent(new CustomEvent("folio:react-agent-request", { detail: e }));
			}
		}, () => {
			window.FolioBridge && (window.FolioBridge.openAgentDock = t);
		};
	}, []);
	async function w() {
		if (!g) {
			_(!0), h("재시작 요청 중");
			try {
				await fetch("/api/server/restart", {
					method: "POST",
					body: "{}"
				});
			} catch {}
			h("서버 재시작 중"), await rf(h), _(!1);
		}
	}
	function T(e) {
		let t = f[e] || Yi(e);
		window.location.hash !== t && (window.location.hash = t);
	}
	function E(e) {
		let t = Xi(e);
		return t.id === "home" ? /* @__PURE__ */ (0, K.jsx)(un, {}) : t.id === "dashboard" ? /* @__PURE__ */ (0, K.jsx)(ns, {}) : t.id === "briefing" ? /* @__PURE__ */ (0, K.jsx)(Wi, {}) : t.id === "rss" ? /* @__PURE__ */ (0, K.jsx)(au, {}) : t.id === "market-memory" ? /* @__PURE__ */ (0, K.jsx)(Rc, {}) : t.id === "analysis" ? /* @__PURE__ */ (0, K.jsx)(So, {}) : t.id === "deep-research" ? /* @__PURE__ */ (0, K.jsx)($s, {}) : t.id === "watchlist" ? /* @__PURE__ */ (0, K.jsx)(Ud, {}) : t.id === "portfolio" ? /* @__PURE__ */ (0, K.jsx)(dl, {}) : t.id === "settings" ? /* @__PURE__ */ (0, K.jsx)(md, {}) : null;
	}
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: `react-shell${i ? " is-nav-collapsed" : ""}${C}${S ? "" : " is-agent-suppressed"}`,
		children: [
			/* @__PURE__ */ (0, K.jsx)("a", {
				className: "react-skip-link",
				href: "#folio-main-content",
				onClick: (e) => {
					e.preventDefault(), window.requestAnimationFrame(() => v.current?.focus({ preventScroll: !0 }));
				},
				children: "본문으로 건너뛰기"
			}),
			/* @__PURE__ */ (0, K.jsxs)("header", {
				className: "react-shell-topbar",
				children: [/* @__PURE__ */ (0, K.jsxs)("button", {
					type: "button",
					className: "react-shell-brand",
					onClick: () => {
						T(r);
					},
					"aria-label": "홈으로 이동",
					children: [/* @__PURE__ */ (0, K.jsx)($t, {}), /* @__PURE__ */ (0, K.jsx)("small", { children: "Investment Workspace" })]
				}), /* @__PURE__ */ (0, K.jsxs)("div", {
					className: "react-shell-status",
					"aria-live": "polite",
					children: [
						/* @__PURE__ */ (0, K.jsx)("span", { children: m }),
						/* @__PURE__ */ (0, K.jsx)(qd, {}),
						/* @__PURE__ */ (0, K.jsx)(Xd, {}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "btn btn--sm",
							type: "button",
							onClick: w,
							disabled: g,
							children: g ? "재시작 중" : "재시작"
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, K.jsxs)("aside", {
				className: "react-shell-nav",
				"aria-label": "주요 화면 탐색",
				children: [/* @__PURE__ */ (0, K.jsx)("button", {
					className: "react-shell-nav-toggle",
					type: "button",
					"aria-label": i ? "좌측 사이드바 펼치기" : "좌측 사이드바 접기",
					"aria-expanded": !i,
					onClick: () => a((e) => !e),
					children: /* @__PURE__ */ (0, K.jsx)("svg", {
						viewBox: "0 0 16 16",
						fill: "none",
						"aria-hidden": "true",
						children: /* @__PURE__ */ (0, K.jsx)("path", { d: "M10 3.5 L5.5 8 L10 12.5" })
					})
				}), /* @__PURE__ */ (0, K.jsxs)("nav", {
					className: "react-left-nav",
					"aria-label": "Folio OS 화면",
					children: [/* @__PURE__ */ (0, K.jsx)("div", {
						className: "react-left-nav-title",
						children: "Navigate"
					}), Zd.map((e) => /* @__PURE__ */ (0, K.jsxs)("section", {
						className: "react-left-nav-group",
						"data-nav-group": e.id,
						children: [e.title && /* @__PURE__ */ (0, K.jsx)("h3", { children: e.title }), /* @__PURE__ */ (0, K.jsx)("div", {
							className: "react-left-nav-items",
							children: e.routes.map((t) => {
								let i = e.title === "Home" ? r : t, a = Ki.find((e) => e.id === i);
								return a ? /* @__PURE__ */ (0, K.jsx)("span", {
									className: "react-left-nav-entry",
									children: /* @__PURE__ */ (0, K.jsxs)("button", {
										type: "button",
										"data-tooltip": a.label,
										"data-qa": a.id === "deep-research" ? "nav-deep-research" : void 0,
										"data-route": a.id,
										className: "react-left-nav-item",
										"aria-current": a.id === n.id ? "page" : void 0,
										onClick: () => {
											T(a.id);
										},
										children: [/* @__PURE__ */ (0, K.jsx)("span", {
											className: "react-left-nav-icon",
											"aria-hidden": "true",
											children: Qd[a.id]
										}), /* @__PURE__ */ (0, K.jsx)("span", {
											className: "react-left-nav-label",
											children: a.label
										})]
									})
								}, a.id) : null;
							})
						})]
					}, e.id))]
				})]
			}),
			/* @__PURE__ */ (0, K.jsx)("main", {
				className: "react-shell-main",
				id: "folio-main-content",
				children: /* @__PURE__ */ (0, K.jsx)("section", {
					className: "react-route-host",
					"data-route": n.id,
					ref: v,
					tabIndex: -1,
					children: Gi.filter((e) => u.has(e.id)).map((e) => /* @__PURE__ */ (0, K.jsx)("div", {
						className: "react-route-pane",
						"data-route-pane": e.id,
						hidden: e.id !== n.id,
						children: E(e.id)
					}, e.id))
				})
			}),
			S && /* @__PURE__ */ (0, K.jsx)(Gl, {
				surface: `react_${n.id}`,
				open: s,
				onOpen: () => c(!0),
				onClose: () => c(!1)
			}),
			/* @__PURE__ */ (0, K.jsx)(ta, {})
		]
	});
}
//#endregion
//#region src/app/AppTour.tsx
var of = [
	{
		route: "rss",
		title: "여기로 자료가 들어옵니다",
		body: "고른 시장의 매체에서 뉴스를 자동으로 모읍니다. 직접 저장한 기사·리포트·공시도 같은 곳에 쌓이고, 전부 검색할 수 있게 정리됩니다."
	},
	{
		route: "market-memory",
		title: "모인 자료가 이야기가 됩니다",
		body: "낱개 기사 대신 지금 시장을 움직이는 흐름으로 묶습니다. 여러 매체가 함께 다룬 것만 흐름이 되고, 그 흐름은 하루로 끝나지 않고 강해지거나 약해지는 상태로 이어집니다."
	},
	{
		route: "briefing",
		title: "이야기가 결과물이 됩니다",
		body: "모인 자료와 흐름으로 매일의 브리핑을 만듭니다. 어떤 자료를 근거로 삼았는지가 함께 남고, 기업 분석과 테마 분석도 같은 자료를 씁니다."
	}
], sf = 340, cf = 14, lf = 12;
function uf(e) {
	return document.querySelector(`.react-left-nav-item[data-route="${e}"]`);
}
function df(e) {
	if (!e) return null;
	let t = e.getBoundingClientRect();
	return t.width < 1 || t.height < 1 ? null : {
		top: t.top,
		left: t.left,
		width: t.width,
		height: t.height
	};
}
function ff(e) {
	if (!e) return {
		top: Math.max(lf, window.innerHeight / 2 - 120),
		left: Math.max(lf, (window.innerWidth - sf) / 2)
	};
	let t = window.innerWidth - (e.left + e.width) - cf >= 352 ? e.left + e.width + cf : Math.min(Math.max(lf, e.left), window.innerWidth - sf - lf);
	return {
		top: Math.min(Math.max(lf, e.top - 8), Math.max(lf, window.innerHeight - 260)),
		left: t
	};
}
function pf({ onDone: e }) {
	let [t, n] = (0, l.useState)(0), [r, i] = (0, l.useState)(null), a = (0, l.useRef)(null), o = (0, l.useRef)(null), s = of[Math.min(t, of.length - 1)];
	(0, l.useEffect)(() => {
		let e = Yi(s.route);
		window.location.hash !== e && (window.location.hash = e);
	}, [s.route]), (0, l.useEffect)(() => {
		let e = !0, t = () => {
			e && i(df(uf(s.route)));
		};
		t();
		let n = [
			60,
			180,
			400
		].map((e) => window.setTimeout(t, e)), r = () => t();
		return window.addEventListener("resize", r), window.addEventListener("scroll", r, !0), () => {
			e = !1, n.forEach((e) => window.clearTimeout(e)), window.removeEventListener("resize", r), window.removeEventListener("scroll", r, !0);
		};
	}, [s.route, t]), (0, l.useEffect)(() => {
		o.current?.focus();
	}, [t]);
	let c = (0, l.useCallback)(() => {
		e();
	}, [e]), u = (e) => {
		if (e.key === "Escape") {
			e.preventDefault(), c();
			return;
		}
		if (e.key !== "Tab") return;
		let t = Array.from(a.current?.querySelectorAll("button:not([disabled])") ?? []);
		if (!t.length) return;
		let [n, r] = [t[0], t[t.length - 1]], i = document.activeElement;
		e.shiftKey && (i === n || !a.current?.contains(i)) ? (e.preventDefault(), r.focus()) : !e.shiftKey && i === r && (e.preventDefault(), n.focus());
	}, d = ff(r), f = t === of.length - 1;
	return /* @__PURE__ */ (0, K.jsxs)("div", {
		className: "tour-layer",
		role: "dialog",
		"aria-modal": "true",
		"aria-labelledby": "tourTitle",
		onKeyDown: u,
		children: [r ? /* @__PURE__ */ (0, K.jsx)("div", {
			className: "tour-spot",
			"aria-hidden": "true",
			style: {
				top: r.top,
				left: r.left,
				width: r.width,
				height: r.height
			}
		}, "spot") : /* @__PURE__ */ (0, K.jsx)("div", {
			className: "tour-scrim",
			"aria-hidden": "true"
		}, "scrim"), /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "tour-card",
			ref: a,
			style: {
				top: d.top,
				left: d.left,
				width: sf
			},
			children: [
				/* @__PURE__ */ (0, K.jsxs)("p", {
					className: "tour-count",
					children: [
						t + 1,
						" / ",
						of.length
					]
				}),
				/* @__PURE__ */ (0, K.jsx)("h2", {
					id: "tourTitle",
					tabIndex: -1,
					ref: o,
					children: s.title
				}),
				/* @__PURE__ */ (0, K.jsx)("p", {
					className: "tour-body",
					children: s.body
				}),
				/* @__PURE__ */ (0, K.jsxs)("div", {
					className: "tour-acts",
					children: [
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "tour-skip",
							type: "button",
							onClick: c,
							children: "끝내기"
						}),
						t > 0 && /* @__PURE__ */ (0, K.jsx)("button", {
							className: "tour-btn",
							type: "button",
							onClick: () => n(t - 1),
							children: "이전"
						}),
						/* @__PURE__ */ (0, K.jsx)("button", {
							className: "tour-btn tour-btn--go",
							type: "button",
							onClick: () => f ? c() : n(t + 1),
							children: f ? "둘러보기 마치기" : "다음"
						})
					]
				})
			]
		})]
	});
}
//#endregion
//#region src/app/WelcomeWizard.tsx
var mf = [
	"welcome",
	"theme",
	"engine",
	"markets",
	"done"
], hf = [
	{
		id: "light",
		label: "라이트"
	},
	{
		id: "dark",
		label: "다크"
	},
	{
		id: "system",
		label: "시스템"
	}
], gf = [
	{
		id: "openai",
		label: "OpenAI",
		url: "https://platform.openai.com/api-keys"
	},
	{
		id: "gemini",
		label: "Gemini",
		url: "https://aistudio.google.com/apikey"
	},
	{
		id: "claude",
		label: "Claude",
		url: "https://console.anthropic.com/settings/keys"
	}
], _f = {
	US: "US",
	KR: "KR",
	EUROPE: "EU",
	JP: "JP"
}, vf = {
	welcome: /* @__PURE__ */ (0, K.jsx)("path", { d: "M3 7.5 12 3l9 4.5-9 4.5zM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5" }),
	theme: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("circle", {
		cx: "12",
		cy: "12",
		r: "8.6"
	}), /* @__PURE__ */ (0, K.jsx)("path", {
		d: "M12 3.4a8.6 8.6 0 0 0 0 17.2z",
		fill: "currentColor",
		stroke: "none"
	})] }),
	engine: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("path", { d: "M12 3.5v3M12 17.5v3M5.4 5.4l2.1 2.1M16.5 16.5l2.1 2.1M3.5 12h3M17.5 12h3M5.4 18.6l2.1-2.1M16.5 7.5l2.1-2.1" }), /* @__PURE__ */ (0, K.jsx)("circle", {
		cx: "12",
		cy: "12",
		r: "3.2"
	})] }),
	markets: /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsx)("circle", {
		cx: "12",
		cy: "12",
		r: "8.6"
	}), /* @__PURE__ */ (0, K.jsx)("path", { d: "M3.4 12h17.2M12 3.4c2.5 2.6 3.8 5.5 3.8 8.6S14.5 18 12 20.6C9.5 18 8.2 15.1 8.2 12S9.5 6 12 3.4z" })] }),
	done: /* @__PURE__ */ (0, K.jsx)("path", { d: "M5 12.6 9.6 17 19 7.6" })
}, yf = {
	welcome: "환영합니다",
	theme: "화면",
	engine: "선택 사항",
	markets: "수집 범위",
	done: "준비 완료"
};
function bf({ step: e }) {
	return /* @__PURE__ */ (0, K.jsx)("svg", {
		viewBox: "0 0 24 24",
		"aria-hidden": "true",
		children: vf[e]
	});
}
function xf({ onFinish: e }) {
	let t = ju(), [n, r] = (0, l.useState)("welcome"), [i, a] = (0, l.useState)(""), [o, s] = (0, l.useState)(""), c = (0, l.useCallback)((e) => {
		s(""), r(e);
	}, []), [u, d] = (0, l.useState)("none"), [f, p] = (0, l.useState)(!1), [m, h] = (0, l.useState)("openai"), [g, _] = (0, l.useState)(""), [v, y] = (0, l.useState)(null), [b, x] = (0, l.useState)(null), [S, C] = (0, l.useState)(null), [w, T] = (0, l.useState)([]), [E, D] = (0, l.useState)(!1), [O, k] = (0, l.useState)(null);
	(0, l.useEffect)(() => {
		let e = !1;
		return (async () => {
			try {
				let t = await B("/api/market-scope");
				if (e) return;
				C(t), T([...t.selected]);
			} catch {}
			try {
				let t = await B("/api/workspace");
				e || k(t);
			} catch {}
			try {
				let t = await B("/api/settings");
				!e && t.agent?.enabled && d(t.agent.mode === "cli" ? "cli" : "api");
			} catch {}
			try {
				let t = await B("/api/agent-bridge/settings");
				e || y(t);
			} catch {}
		})(), () => {
			e = !0;
		};
	}, []);
	let A = (0, l.useCallback)((e) => {
		p(!0), d(e);
	}, []), j = (0, l.useCallback)(async (t) => {
		a("finish");
		try {
			await V("/api/onboarding/complete", { skipped: t });
		} catch {} finally {
			a(""), e(!t && b === !0);
		}
	}, [e, b]), M = async () => {
		if (!f) {
			c("markets");
			return;
		}
		a("engine"), s("");
		try {
			await V("/api/settings", {
				agent: {
					enabled: u !== "none",
					mode: u === "cli" ? "cli" : "api"
				},
				...u === "api" && g.trim() ? { llm: {
					provider: m,
					providers: { [m]: { apiKey: g.trim() } }
				} } : {}
			}), _(""), c("markets");
		} catch (e) {
			s(e instanceof Error ? e.message : "저장하지 못했습니다.");
		} finally {
			a("");
		}
	}, N = async () => {
		if (!S || !w.length) {
			c("done");
			return;
		}
		a("markets"), s("");
		try {
			let e = await te("/api/market-scope", { selected: w });
			D(!!e.newlyEnabled?.length), c("done");
		} catch (e) {
			s(e instanceof Error ? e.message : "저장하지 못했습니다.");
		} finally {
			a("");
		}
	}, P = (e) => {
		T((t) => {
			let n = t.includes(e) ? t.filter((t) => t !== e) : [...t, e];
			return n.length ? n : t;
		});
	}, F = (0, l.useRef)(null), I = () => Array.from(F.current?.querySelectorAll("button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex=\"-1\"])") ?? []);
	(0, l.useEffect)(() => {
		F.current?.querySelector("h1")?.focus();
	}, [n]);
	let L = (e) => {
		if (e.key === "Escape") {
			e.preventDefault(), j(!0);
			return;
		}
		if (e.key !== "Tab") return;
		let t = I();
		if (!t.length) return;
		let [n, r] = [t[0], t[t.length - 1]], i = document.activeElement, a = F.current?.querySelector("h1") ?? null;
		e.shiftKey && (i === n || i === a || !F.current?.contains(i)) ? (e.preventDefault(), r.focus()) : !e.shiftKey && i === r && (e.preventDefault(), n.focus());
	}, R = mf.indexOf(n), z = gf.find((e) => e.id === m);
	return /* @__PURE__ */ (0, K.jsx)("div", {
		className: "welcome-shell",
		role: "dialog",
		"aria-modal": "true",
		"aria-labelledby": "welcomeTitle",
		ref: F,
		onKeyDown: L,
		children: /* @__PURE__ */ (0, K.jsxs)("div", {
			className: "welcome-card",
			children: [
				/* @__PURE__ */ (0, K.jsxs)("header", {
					className: "welcome-head",
					children: [/* @__PURE__ */ (0, K.jsx)($t, {}), /* @__PURE__ */ (0, K.jsxs)("p", {
						className: "welcome-count",
						children: [
							"단계 ",
							/* @__PURE__ */ (0, K.jsx)("b", { children: R + 1 }),
							" / ",
							mf.length
						]
					})]
				}),
				/* @__PURE__ */ (0, K.jsx)("div", {
					className: "welcome-rule",
					role: "progressbar",
					"aria-label": "진행 단계",
					"aria-valuemin": 1,
					"aria-valuemax": mf.length,
					"aria-valuenow": R + 1,
					style: { "--welcome-fill": `${(R + 1) / mf.length * 100}%` }
				}),
				/* @__PURE__ */ (0, K.jsxs)("section", {
					className: "welcome-body",
					children: [
						/* @__PURE__ */ (0, K.jsxs)("p", {
							className: "welcome-eyebrow",
							children: [/* @__PURE__ */ (0, K.jsx)(bf, { step: n }), yf[n]]
						}),
						n === "welcome" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsx)("h1", {
								id: "welcomeTitle",
								tabIndex: -1,
								children: "내 PC 안의 투자 리서치 작업실"
							}),
							/* @__PURE__ */ (0, K.jsxs)("p", { children: [
								"뉴스·공시·리포트를 이 컴퓨터에 모아 읽고, 매일 브리핑과 기업 분석을 만듭니다.",
								" ",
								/* @__PURE__ */ (0, K.jsx)("strong", { children: "자료와 보고서는 전부 이 컴퓨터에만 저장됩니다." })
							] }),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "몇 가지만 정하면 바로 쓸 수 있습니다. 전부 나중에 설정에서 바꿀 수 있고, 건너뛰어도 앱은 그대로 동작합니다."
							})
						] }),
						n === "theme" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsx)("h1", {
								id: "welcomeTitle",
								tabIndex: -1,
								children: "어떤 화면으로 보시겠어요?"
							}),
							/* @__PURE__ */ (0, K.jsxs)("p", { children: [
								"고르는 즉시 바뀝니다. ",
								/* @__PURE__ */ (0, K.jsx)("strong", { children: "시스템" }),
								"을 고르면 이 컴퓨터의 밝게·어둡게 설정을 따라갑니다."
							] }),
							/* @__PURE__ */ (0, K.jsx)("div", {
								className: "welcome-choices",
								role: "group",
								"aria-label": "화면 테마",
								children: hf.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
									type: "button",
									"aria-pressed": t.preference === e.id,
									onClick: () => t.setPreference(e.id),
									children: e.label
								}, e.id))
							}),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "이 설정은 이 브라우저에만 저장됩니다. 상단바의 테마 버튼으로 언제든 바꿀 수 있습니다."
							})
						] }),
						n === "engine" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsx)("h1", {
								id: "welcomeTitle",
								tabIndex: -1,
								children: "AI를 쓰시겠어요?"
							}),
							/* @__PURE__ */ (0, K.jsxs)("p", { children: [
								"브리핑·기업 분석·테마 분석의 문장을 AI가 씁니다.",
								" ",
								/* @__PURE__ */ (0, K.jsx)("strong", { children: "AI가 없어도 앱은 그대로 동작합니다" }),
								" — 자료 수집·검색·차트는 모두 규칙으로 만들고, 보고서도 규칙 기반으로 나옵니다."
							] }),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "welcome-choices",
								role: "group",
								"aria-label": "생성 방식",
								children: [
									/* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": u === "none",
										onClick: () => A("none"),
										children: "AI 없이"
									}),
									/* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": u === "cli",
										onClick: () => A("cli"),
										children: "CLI"
									}),
									/* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": u === "api",
										onClick: () => A("api"),
										children: "API"
									})
								]
							}),
							u === "none" && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "규칙으로 보고서를 만듭니다. 자료 수집·검색·차트는 그대로 동작합니다. 나중에 설정에서 언제든 켤 수 있습니다."
							}),
							u === "api" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
								/* @__PURE__ */ (0, K.jsxs)("p", {
									className: "welcome-muted",
									children: [/* @__PURE__ */ (0, K.jsx)("b", { children: "제공사 서버를 부르는 열쇠" }), "입니다. 설치할 것이 없는 대신 쓴 만큼 요금이 붙습니다. 지금 넣지 않아도 되고, 설정에서 나중에 넣어도 됩니다."]
								}),
								/* @__PURE__ */ (0, K.jsx)("div", {
									className: "welcome-choices",
									role: "group",
									"aria-label": "제공사",
									children: gf.map((e) => /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"aria-pressed": m === e.id,
										onClick: () => h(e.id),
										children: e.label
									}, e.id))
								}),
								/* @__PURE__ */ (0, K.jsxs)("label", {
									className: "welcome-field",
									children: [/* @__PURE__ */ (0, K.jsx)("span", { children: "API 키" }), /* @__PURE__ */ (0, K.jsx)("input", {
										type: "password",
										value: g,
										autoComplete: "off",
										placeholder: "나중에 설정에서 넣어도 됩니다",
										onChange: (e) => _(e.target.value)
									})]
								}),
								/* @__PURE__ */ (0, K.jsxs)("p", {
									className: "welcome-muted",
									children: [
										"키는 이 PC의 ",
										/* @__PURE__ */ (0, K.jsx)("code", { children: ".env" }),
										" 파일에만 저장됩니다. 발급:",
										" ",
										/* @__PURE__ */ (0, K.jsxs)("a", {
											href: z?.url,
											target: "_blank",
											rel: "noreferrer",
											children: [z?.label, " 키 페이지"]
										})
									]
								})
							] }),
							u === "cli" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsxs)("p", {
								className: "welcome-muted",
								children: [/* @__PURE__ */ (0, K.jsx)("b", { children: "내 컴퓨터에 설치해서 쓰는 AI 프로그램" }), "입니다(Codex·Claude Code·Antigravity). 이미 구독 중이라면 추가 요금이 없고, 한 번 실행에 수십 초가 걸립니다. 아래에서 바로 설치하고 로그인할 수 있습니다."]
							}), /* @__PURE__ */ (0, K.jsx)(pu, {
								adapters: v?.adapters ?? [],
								onSettings: y,
								disabled: !!i
							})] })
						] }),
						n === "markets" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsx)("h1", {
								id: "welcomeTitle",
								tabIndex: -1,
								children: "어느 시장을 보시겠어요?"
							}),
							/* @__PURE__ */ (0, K.jsx)("p", { children: "여기서 끈 시장은 자료 수집이 멈추고 화면 전체에서 숨습니다. 유가·달러 같은 글로벌 자료는 항상 보입니다." }),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "US 뉴욕·나스닥 · KR 코스피·코스닥 · EU 런던·프랑크푸르트 · JP 도쿄"
							}),
							S ? /* @__PURE__ */ (0, K.jsx)("div", {
								className: "welcome-markets",
								role: "group",
								"aria-label": "수집·표시할 시장",
								children: S.markets.map((e) => {
									let t = _f[e.id] ?? e.id;
									return /* @__PURE__ */ (0, K.jsx)("button", {
										type: "button",
										"data-code": t,
										"aria-label": `${t} ${e.label}`,
										"aria-pressed": w.includes(e.id),
										onClick: () => P(e.id),
										children: t
									}, e.id);
								})
							}) : /* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "관심 시장 설정을 읽지 못했습니다. 설정 탭에서 정할 수 있습니다."
							}),
							/* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "저장하면 고른 시장의 뉴스를 바로 모으기 시작합니다. 몇 분 걸리고, 그동안에도 다른 화면을 쓸 수 있습니다."
							})
						] }),
						n === "done" && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
							/* @__PURE__ */ (0, K.jsx)("h1", {
								id: "welcomeTitle",
								tabIndex: -1,
								children: "이제 시작할 수 있습니다"
							}),
							E && /* @__PURE__ */ (0, K.jsx)("p", { children: "뉴스를 모으고 있습니다. 상단 진행 표시에서 상태를 볼 수 있습니다." }),
							/* @__PURE__ */ (0, K.jsxs)("ol", {
								className: "welcome-next",
								children: [
									/* @__PURE__ */ (0, K.jsx)("li", { children: /* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "워치리스트" }), "에 관심 종목을 넣으면 그 종목 뉴스가 모입니다."] }) }),
									/* @__PURE__ */ (0, K.jsx)("li", { children: /* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "브리핑" }), "에서 오늘의 시장을 정리합니다. 자료가 쌓일수록 좋아집니다."] }) }),
									/* @__PURE__ */ (0, K.jsx)("li", { children: /* @__PURE__ */ (0, K.jsxs)("span", { children: [/* @__PURE__ */ (0, K.jsx)("strong", { children: "기업 분석" }), "에 티커를 넣으면 공시와 숫자로 보고서를 만듭니다."] }) })
								]
							}),
							O && /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [/* @__PURE__ */ (0, K.jsxs)("p", {
								className: "welcome-path",
								children: [
									/* @__PURE__ */ (0, K.jsx)("b", { children: "자료 저장 위치" }),
									" · ",
									O.path
								]
							}), !O.outsideAppFolder && /* @__PURE__ */ (0, K.jsx)("p", {
								className: "welcome-muted",
								children: "새 버전은 새 폴더로 풀립니다. 설정 > 자료 위치에서 옮겨두면 업데이트할 때 그대로 이어집니다."
							})] }),
							/* @__PURE__ */ (0, K.jsxs)("div", {
								className: "welcome-ask",
								children: [
									/* @__PURE__ */ (0, K.jsx)("p", {
										className: "welcome-ask-q",
										children: "둘러보기를 진행할까요?"
									}),
									/* @__PURE__ */ (0, K.jsx)("p", {
										className: "welcome-muted",
										children: "RSS 피드 · 시장 내러티브 · 브리핑을 차례로 열어, 자료가 어떻게 결과물이 되는지 실제 화면에서 보여드립니다. 30초면 끝나고 언제든 멈출 수 있습니다."
									}),
									/* @__PURE__ */ (0, K.jsxs)("div", {
										className: "welcome-choices",
										role: "group",
										"aria-label": "둘러보기",
										children: [/* @__PURE__ */ (0, K.jsx)("button", {
											type: "button",
											"aria-pressed": b === !0,
											onClick: () => x(!0),
											children: "둘러보기"
										}), /* @__PURE__ */ (0, K.jsx)("button", {
											type: "button",
											"aria-pressed": b === !1,
											onClick: () => x(!1),
											children: "바로 시작"
										})]
									})
								]
							})
						] }),
						o && /* @__PURE__ */ (0, K.jsx)("p", {
							className: "react-dashboard-warning",
							role: "status",
							children: o
						})
					]
				}),
				/* @__PURE__ */ (0, K.jsxs)("footer", {
					className: "welcome-actions",
					children: [/* @__PURE__ */ (0, K.jsx)("button", {
						className: "welcome-skip",
						type: "button",
						onClick: () => void j(n !== "done"),
						disabled: !!i,
						children: n === "done" ? "닫기" : "건너뛰기"
					}), /* @__PURE__ */ (0, K.jsxs)("div", {
						className: "welcome-acts",
						children: [
							R > 0 && n !== "done" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn",
								type: "button",
								onClick: () => c(mf[R - 1]),
								disabled: !!i,
								children: "이전"
							}),
							n === "welcome" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn welcome-btn--go",
								type: "button",
								onClick: () => c("theme"),
								children: "다음"
							}),
							n === "theme" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn welcome-btn--go",
								type: "button",
								onClick: () => c("engine"),
								children: "다음"
							}),
							n === "engine" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn welcome-btn--go",
								type: "button",
								onClick: () => void M(),
								disabled: !!i,
								children: i === "engine" ? "저장 중" : "저장하고 다음"
							}),
							n === "markets" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn welcome-btn--go",
								type: "button",
								onClick: () => void N(),
								disabled: !!i,
								children: i === "markets" ? "저장 중" : "저장하고 시작"
							}),
							n === "done" && /* @__PURE__ */ (0, K.jsx)("button", {
								className: "welcome-btn welcome-btn--go",
								type: "button",
								onClick: () => void j(!1),
								disabled: !!i,
								children: b ? "둘러보기 시작" : "시작하기"
							})
						]
					})]
				})
			]
		})
	});
}
//#endregion
//#region src/app/App.tsx
function Sf() {
	let [e, t] = (0, l.useState)(!1), [n, r] = (0, l.useState)(!1);
	return (0, l.useEffect)(() => {
		let e = !1;
		return (async () => {
			try {
				let n = await B("/api/onboarding");
				!e && n.firstRun && t(!0);
			} catch {}
		})(), () => {
			e = !0;
		};
	}, []), (0, l.useEffect)(() => {
		let e = () => t(!0);
		return window.addEventListener("folio:show-welcome", e), () => window.removeEventListener("folio:show-welcome", e);
	}, []), /* @__PURE__ */ (0, K.jsxs)(K.Fragment, { children: [
		/* @__PURE__ */ (0, K.jsx)(af, {}),
		e && /* @__PURE__ */ (0, K.jsx)(xf, { onFinish: (e) => {
			t(!1), r(e);
		} }),
		n && /* @__PURE__ */ (0, K.jsx)(pf, { onDone: () => r(!1) })
	] });
}
//#endregion
//#region src/main.tsx
var Cf = { "market-state": () => /* @__PURE__ */ (0, K.jsx)(yc, {}) };
function wf() {
	document.querySelectorAll("[data-react-island]").forEach((e) => {
		let t = Cf[e.dataset.reactIsland || ""];
		!t || e.dataset.reactMounted === "1" || (e.dataset.reactMounted = "1", (0, u.createRoot)(e).render(/* @__PURE__ */ (0, K.jsx)(l.StrictMode, { children: t() })));
	});
}
function Tf() {
	let e = document.getElementById("folioReactRoot");
	return e ? e.dataset.reactMounted === "1" || (e.dataset.reactMounted = "1", (0, u.createRoot)(e).render(/* @__PURE__ */ (0, K.jsx)(l.StrictMode, { children: /* @__PURE__ */ (0, K.jsx)(Sf, {}) })), !0) : !1;
}
function Ef() {
	Tf(), wf();
}
document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", Ef) : Ef();
//#endregion
