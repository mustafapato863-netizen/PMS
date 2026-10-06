/**
 * Real `options` output of PR #14's `InsightsService._options` (tip 3deccd2),
 * captured from a throwaway merge of #13 + #14 onto main @ 0d4d48d with a
 * small June/May record set (Pharmacy only has May data). Regenerate with the
 * script in /workspace/pms-insights-cascade-review/v2/pr14_shape.py.
 */
export const pr14Options = {
  "default": {
    "regions": [
      "EGY",
      "UAE"
    ],
    "teams": [
      "Call Center",
      "Coding",
      "Inbound",
      "Marketing",
      "Outbound",
      "Pre-Approvals IP Elective Dubai",
      "Pre-Approvals IP Final Dubai",
      "Pre-Approvals IP Offshore",
      "Pre-Approvals OP Dubai",
      "Pre-Approvals OP Final SHJAJM",
      "Sales"
    ],
    "performance_levels": [
      "Employee",
      "Managerial"
    ],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Call Center": [
        "Call Center"
      ],
      "Coding": [
        "RCM"
      ],
      "Inbound": [
        "Call Center"
      ],
      "Marketing": [
        "Marketing"
      ],
      "Outbound": [
        "Call Center"
      ],
      "Pre-Approvals IP Elective Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Final Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ],
      "Pre-Approvals OP Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Final SHJAJM": [
        "RCM",
        "Pre-Approvals"
      ],
      "Sales": [
        "Sales"
      ]
    }
  },
  "juneTeamPharmacy": {
    "regions": [],
    "teams": [
      "Call Center",
      "Coding",
      "Inbound",
      "Marketing",
      "Outbound",
      "Pre-Approvals IP Elective Dubai",
      "Pre-Approvals IP Final Dubai",
      "Pre-Approvals IP Offshore",
      "Pre-Approvals OP Dubai",
      "Pre-Approvals OP Final SHJAJM",
      "Sales"
    ],
    "performance_levels": [],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Call Center": [
        "Call Center"
      ],
      "Coding": [
        "RCM"
      ],
      "Inbound": [
        "Call Center"
      ],
      "Marketing": [
        "Marketing"
      ],
      "Outbound": [
        "Call Center"
      ],
      "Pre-Approvals IP Elective Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Final Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ],
      "Pre-Approvals OP Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Final SHJAJM": [
        "RCM",
        "Pre-Approvals"
      ],
      "Sales": [
        "Sales"
      ]
    }
  },
  "inboundCorporate": {
    "regions": [],
    "teams": [],
    "performance_levels": [
      "Employee"
    ],
    "functions": [],
    "team_functions": {}
  },
  "egySales": {
    "regions": [
      "UAE"
    ],
    "teams": [
      "Coding",
      "Inbound",
      "Pre-Approvals IP Offshore"
    ],
    "performance_levels": [],
    "functions": [
      "Call Center",
      "RCM"
    ],
    "team_functions": {
      "Coding": [
        "RCM"
      ],
      "Inbound": [
        "Call Center"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ]
    }
  },
  "egyNoFilters": {
    "regions": [
      "EGY",
      "UAE"
    ],
    "teams": [
      "Coding",
      "Inbound",
      "Pre-Approvals IP Offshore"
    ],
    "performance_levels": [
      "Employee"
    ],
    "functions": [
      "Call Center",
      "RCM"
    ],
    "team_functions": {
      "Coding": [
        "RCM"
      ],
      "Inbound": [
        "Call Center"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ]
    }
  }
} as const;

/**
 * Real `options` from merged main (8d0aa42) when the app sends `function=`
 * (PR #17): `teams` / `team_functions` are narrowed to the function, while
 * `functions` ignores the function and team. Same record set; regenerate with
 * /workspace/pms-insights-p3-review/pr17_shape.py.
 */
export const pr17FunctionOptions = {
  "functionCallCenter": {
    "regions": [
      "EGY",
      "UAE"
    ],
    "teams": [
      "Call Center",
      "Inbound",
      "Outbound"
    ],
    "performance_levels": [
      "Employee",
      "Managerial"
    ],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Call Center": [
        "Call Center"
      ],
      "Inbound": [
        "Call Center"
      ],
      "Outbound": [
        "Call Center"
      ]
    }
  },
  "functionRcm": {
    "regions": [
      "EGY",
      "UAE"
    ],
    "teams": [
      "Coding",
      "Pre-Approvals IP Elective Dubai",
      "Pre-Approvals IP Final Dubai",
      "Pre-Approvals IP Offshore",
      "Pre-Approvals OP Dubai",
      "Pre-Approvals OP Final SHJAJM"
    ],
    "performance_levels": [
      "Employee",
      "Managerial"
    ],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Coding": [
        "RCM"
      ],
      "Pre-Approvals IP Elective Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Final Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ],
      "Pre-Approvals OP Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Final SHJAJM": [
        "RCM",
        "Pre-Approvals"
      ]
    }
  },
  "functionRcmTeamCoding": {
    "regions": [
      "EGY"
    ],
    "teams": [
      "Coding",
      "Pre-Approvals IP Elective Dubai",
      "Pre-Approvals IP Final Dubai",
      "Pre-Approvals IP Offshore",
      "Pre-Approvals OP Dubai",
      "Pre-Approvals OP Final SHJAJM"
    ],
    "performance_levels": [
      "Employee"
    ],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Coding": [
        "RCM"
      ],
      "Pre-Approvals IP Elective Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Final Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Offshore": [
        "RCM"
      ],
      "Pre-Approvals OP Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Final SHJAJM": [
        "RCM",
        "Pre-Approvals"
      ]
    }
  },
  "functionPreApprovals": {
    "regions": [
      "UAE"
    ],
    "teams": [
      "Pre-Approvals IP Elective Dubai",
      "Pre-Approvals IP Final Dubai",
      "Pre-Approvals OP Dubai",
      "Pre-Approvals OP Final SHJAJM"
    ],
    "performance_levels": [
      "Employee",
      "Managerial"
    ],
    "functions": [
      "Call Center",
      "Marketing",
      "Pre-Approvals",
      "RCM",
      "Sales"
    ],
    "team_functions": {
      "Pre-Approvals IP Elective Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals IP Final Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Dubai": [
        "RCM",
        "Pre-Approvals"
      ],
      "Pre-Approvals OP Final SHJAJM": [
        "RCM",
        "Pre-Approvals"
      ]
    }
  }
} as const;
