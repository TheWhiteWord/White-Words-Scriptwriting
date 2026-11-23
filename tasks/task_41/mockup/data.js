/* Mockup data, produced by core/trash.trash_for_ui / trash_detail / purge_preview
   on a throwaway copy of tests/fixtures/save-the-children (gen_mockup_data.py).
   A build artefact of the mockup, not sample data written by hand. */
window.MOCKUP = {
 "list": {
  "success": true,
  "count": 6,
  "entities": 9,
  "counts_by_type": {
   "scene": 2,
   "scene_beats": 2,
   "character": 1,
   "location": 2,
   "world": 1,
   "plot": 1
  },
  "purge_older_than_days": 30,
  "items": [
   {
    "type": "world",
    "id": "the-i",
    "name": "The I",
    "deleted_at": "2026-11-23T15:22:08+00:00",
    "purge_eligible": false,
    "includes": [
     {
      "type": "location",
      "id": "the-central-room",
      "name": "The Central Room",
      "label": "Location"
     },
     {
      "type": "location",
      "id": "the-garden",
      "name": "The Garden",
      "label": "Location"
     }
    ],
    "label": "World",
    "preview": "A simulation environment where developing consciousness forms.",
    "has_script": false,
    "restore": {
     "blockers": [],
     "warnings": {},
     "returned": {
      "children": [
       {
        "type": "location",
        "id": "the-central-room",
        "name": "The Central Room"
       },
       {
        "type": "location",
        "id": "the-garden",
        "name": "The Garden"
       }
      ],
      "relations": 0,
      "sections": 8,
      "referenced_by": []
     }
    }
   },
   {
    "type": "scene",
    "id": "central-room-day",
    "name": "Central Room - Day",
    "deleted_at": "2026-11-22T10:05:00+00:00",
    "purge_eligible": false,
    "includes": [],
    "label": "Scene",
    "preview": "INT. THE CENTRAL ROOM - DAY",
    "has_script": true,
    "restore": {
     "blockers": [],
     "warnings": {
      "reference_in_trash": [
       {
        "entity_type": "location",
        "id": "the-central-room",
        "name": "The Central Room",
        "field": "location"
       },
       {
        "entity_type": "character",
        "id": "kael",
        "name": "Kael",
        "field": "character_scene"
       },
       {
        "entity_type": "location",
        "id": "the-central-room",
        "name": "The Central Room",
        "field": "location_scene"
       },
       {
        "entity_type": "plot",
        "id": "the-resistance",
        "name": "The Resistance",
        "field": "plot_inciting_incident"
       }
      ],
      "stranded_children": [
       {
        "entity_type": "scene_beats",
        "id": "central-room-day-beats",
        "field": "parent",
        "name": "central-room-day-beats"
       }
      ]
     },
     "returned": {
      "children": [],
      "relations": 0,
      "sections": 8,
      "referenced_by": [
       {
        "entity_type": "relationship",
        "id": "kael-mira",
        "name": "Kael & Mira",
        "field": ""
       },
       {
        "entity_type": "relationship",
        "id": "kael-the-administrator",
        "name": "Kael & The Administrator",
        "field": ""
       }
      ]
     }
    }
   },
   {
    "type": "character",
    "id": "kael",
    "name": "Kael",
    "deleted_at": "2026-11-21T18:02:00+00:00",
    "purge_eligible": false,
    "includes": [],
    "label": "Character",
    "preview": "A young person inside The I who begins to feel the system is wrong.",
    "has_script": false,
    "restore": {
     "blockers": [],
     "warnings": {
      "reference_in_trash": [
       {
        "entity_type": "scene",
        "id": "central-room-day",
        "name": "Central Room - Day",
        "field": "character_scene"
       },
       {
        "entity_type": "scene",
        "id": "central-room-night",
        "name": "Central Room - Night",
        "field": "character_scene"
       }
      ]
     },
     "returned": {
      "children": [],
      "relations": 0,
      "sections": 9,
      "referenced_by": [
       {
        "entity_type": "relationship",
        "id": "kael-mira",
        "name": "Kael & Mira",
        "field": ""
       },
       {
        "entity_type": "relationship",
        "id": "kael-the-administrator",
        "name": "Kael & The Administrator",
        "field": ""
       }
      ]
     }
    }
   },
   {
    "type": "scene",
    "id": "central-room-night",
    "name": "Central Room - Night",
    "deleted_at": "2026-11-20T09:15:00+00:00",
    "purge_eligible": false,
    "includes": [
     {
      "type": "scene_beats",
      "id": "central-room-night-beats",
      "name": "central-room-night-beats",
      "label": "Scene Beats"
     }
    ],
    "label": "Scene",
    "preview": "INT. THE CENTRAL ROOM - NIGHT",
    "has_script": true,
    "restore": {
     "blockers": [],
     "warnings": {
      "reference_in_trash": [
       {
        "entity_type": "location",
        "id": "the-central-room",
        "name": "The Central Room",
        "field": "location"
       },
       {
        "entity_type": "character",
        "id": "kael",
        "name": "Kael",
        "field": "character_scene"
       },
       {
        "entity_type": "location",
        "id": "the-central-room",
        "name": "The Central Room",
        "field": "location_scene"
       },
       {
        "entity_type": "plot",
        "id": "the-resistance",
        "name": "The Resistance",
        "field": "plot_climax"
       }
      ]
     },
     "returned": {
      "children": [
       {
        "type": "scene_beats",
        "id": "central-room-night-beats",
        "name": "central-room-night-beats"
       }
      ],
      "relations": 0,
      "sections": 8,
      "referenced_by": [
       {
        "entity_type": "relationship",
        "id": "kael-mira",
        "name": "Kael & Mira",
        "field": ""
       },
       {
        "entity_type": "relationship",
        "id": "mira-the-administrator",
        "name": "Mira & The Administrator",
        "field": ""
       }
      ]
     }
    }
   },
   {
    "type": "scene_beats",
    "id": "central-room-day-beats",
    "name": "central-room-day-beats",
    "deleted_at": "2026-11-14T21:40:00+00:00",
    "purge_eligible": false,
    "includes": [],
    "label": "Scene Beats",
    "preview": "central-room-day-beats",
    "has_script": false,
    "restore": {
     "blockers": [
      {
       "code": "parent_trashed",
       "message": "“Central Room - Day” is still in the trash. Restore it too, or this comes back where nothing can see it.",
       "fix": {
        "entity_type": "scene",
        "id": "central-room-day",
        "name": "Central Room - Day"
       }
      }
     ],
     "warnings": {},
     "returned": {
      "children": [],
      "relations": 0,
      "sections": 1,
      "referenced_by": []
     }
    }
   },
   {
    "type": "plot",
    "id": "the-resistance",
    "name": "The Resistance",
    "deleted_at": "2026-09-21T08:00:00+00:00",
    "purge_eligible": true,
    "includes": [],
    "label": "Plot",
    "preview": "Kael and Mira organize the children to breach the Central Room.",
    "has_script": false,
    "restore": {
     "blockers": [],
     "warnings": {
      "reference_in_trash": [
       {
        "entity_type": "scene",
        "id": "central-room-night",
        "name": "Central Room - Night",
        "field": "plot_climax"
       },
       {
        "entity_type": "scene",
        "id": "central-room-day",
        "name": "Central Room - Day",
        "field": "plot_inciting_incident"
       },
       {
        "entity_type": "character",
        "id": "kael",
        "name": "Kael",
        "field": "characters"
       }
      ]
     },
     "returned": {
      "children": [],
      "relations": 0,
      "sections": 6,
      "referenced_by": []
     }
    }
   }
  ]
 },
 "blocked": {
  "entity": {
   "id": "central-room-day-beats",
   "type": "scene_beats",
   "name": "central-room-day-beats",
   "label": "Scene Beats",
   "deleted_at": "2026-11-14T21:40:00+00:00",
   "one_sentence": "",
   "has_script": false,
   "fields": {
    "name": "",
    "one_sentence": "",
    "status": "",
    "order_key": 0.0,
    "parent": {
     "id": "central-room-day",
     "entity_type": "scene",
     "name": "Central Room - Day"
    },
    "location": null
   },
   "extra": {
    "type": "scene_beats",
    "driver": "kael",
    "scene_objective": "Find out whether the door was ever locked.",
    "turning_point": "The handle turns. The lock was never engaged.",
    "true_character": [
     {
      "character": "kael",
      "dilemma": "Open the door and become the one who broke it, or leave it shut and stay innocent of it.",
      "choice_reveals": "He needs the truth more than he needs to be innocent of it."
     }
    ],
    "changes": [
     {
      "entity": "kael",
      "change": "No longer believes the door was locked; suspects the story he was told was the lock."
     },
     {
      "entity": "the-central-room",
      "change": "Stops being a boundary and becomes an exit."
     }
    ],
    "beats": [
     {
      "action": {
       "by": "kael",
       "surface": "Hand flat on the door",
       "subtext": "testing whether it will hold"
      },
      "reaction": {
       "by": "kael",
       "surface": "It turns",
       "subtext": "discovering his own prison was agreed, not built"
      },
      "gap": "He expected resistance and got none."
     },
     {
      "action": {
       "by": "the-central-room",
       "surface": "The room beyond is lit",
       "subtext": "offering a version of home back to him"
      },
      "reaction": {
       "by": "kael",
       "surface": "He steps back",
       "subtext": "refusing the bargain the room is making"
      }
     }
    ]
   }
  },
  "includes": [],
  "sections": {
   "Notes": "The lock is the scene's whole mechanism: the door was never locked, so the\ncage was agreement. The gap opens in the first beat — action and reaction\nboth Kael, which is why the exchange draws it as inner conflict — and the\nsecond beat puts the room itself on a lane, so the circumstance is a\nparticipant rather than scenery."
  },
  "relations": {
   "out": [],
   "in": [],
   "all": []
  },
  "referenced_by": [],
  "restore": {
   "blockers": [
    {
     "code": "parent_trashed",
     "message": "“Central Room - Day” is still in the trash. Restore it too, or this comes back where nothing can see it.",
     "fix": {
      "entity_type": "scene",
      "id": "central-room-day",
      "name": "Central Room - Day"
     }
    }
   ],
   "warnings": {},
   "returned": {
    "children": [],
    "relations": 0,
    "sections": 1,
    "referenced_by": []
   }
  },
  "purge": {
   "items": [
    {
     "id": "central-room-day-beats",
     "type": "scene_beats",
     "name": "central-room-day-beats",
     "label": "Scene Beats"
    }
   ],
   "affected": [],
   "backup": true,
   "refusal": null
  }
 },
 "bundle": {
  "entity": {
   "id": "central-room-night",
   "type": "scene",
   "name": "Central Room - Night",
   "label": "Scene",
   "deleted_at": "2026-11-20T09:15:00+00:00",
   "one_sentence": "",
   "has_script": true,
   "fields": {
    "name": "Central Room - Night",
    "one_sentence": "",
    "status": "drafted",
    "order_key": 2.0,
    "parent": {
     "id": "seq-discovery",
     "entity_type": "sequence",
     "name": "The Discovery"
    },
    "location": {
     "id": "the-central-room",
     "entity_type": "location",
     "name": "The Central Room"
    }
   },
   "extra": {
    "act_id": "act-1",
    "dramatic_role": "plot_role",
    "int_ext": "INT.",
    "time_of_day": "NIGHT",
    "type": "scene",
    "value_turns": [
     {
      "plot": "the-resistance",
      "value": "freedom",
      "from": "free",
      "to": "free",
      "effects": [
       {
        "character": "kael",
        "levels": [
         {
          "conflict_level": "inner",
          "effect": "Refusing the offer is the deepening: the change is in how the choice lands, not in the state — freedom now has a cost attached to it."
         },
         {
          "conflict_level": "personal",
          "effect": "The offer makes the known world real again by putting a price on leaving it."
         }
        ]
       },
       {
        "character": "mira",
        "levels": [
         {
          "conflict_level": "inner",
          "effect": "Mira, unseen in the room, is given the same choice and must answer it alone."
         }
        ]
       }
      ]
     },
     {
      "plot": "the-resistance",
      "value": "trust",
      "from": "open",
      "to": "open",
      "effects": [
       {
        "character": "kael",
        "levels": [
         {
          "conflict_level": "inner",
          "effect": "The Administrator speaks with a reasonable voice, so Kael's judgement of it has to become his own rather than borrowed."
         }
        ]
       }
      ]
     }
    ]
   }
  },
  "includes": [
   {
    "id": "central-room-night-beats",
    "entity_type": "scene_beats",
    "name": "central-room-night-beats",
    "type": "scene_beats",
    "label": "Scene Beats"
   }
  ],
  "sections": {
   "Beats": "",
   "Conflict": "",
   "Content": "The ADMINISTRATOR speaks from everywhere and nowhere. Kael listens. Then shakes their head.",
   "Dramatic Function": "The sequence climax. Kael chooses the unknown over the known.",
   "Notes": "The Administrator's voice is calm, reasonable, and utterly alien.",
   "Objective": "[placeholder — scene/Objective]",
   "Production": "[placeholder — scene/Production]",
   "Value Turn": "[placeholder — scene/Value Turn]"
  },
  "relations": {
   "out": [],
   "in": [
    {
     "id": "kael",
     "entity_type": "",
     "name": "kael",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-central-room",
     "entity_type": "location",
     "name": "The Central Room",
     "kind": "location_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-resistance",
     "entity_type": "",
     "name": "the-resistance",
     "kind": "plot_climax",
     "note": "The Administrator makes its final offer. Kael refuses.",
     "live": false
    }
   ],
   "all": [
    {
     "id": "kael",
     "entity_type": "",
     "name": "kael",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-central-room",
     "entity_type": "location",
     "name": "The Central Room",
     "kind": "location_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-resistance",
     "entity_type": "",
     "name": "the-resistance",
     "kind": "plot_climax",
     "note": "The Administrator makes its final offer. Kael refuses.",
     "live": false
    }
   ]
  },
  "referenced_by": [
   {
    "entity_type": "relationship",
    "id": "kael-mira",
    "name": "Kael & Mira",
    "field": ""
   },
   {
    "entity_type": "relationship",
    "id": "mira-the-administrator",
    "name": "Mira & The Administrator",
    "field": ""
   }
  ],
  "restore": {
   "blockers": [],
   "warnings": {
    "reference_in_trash": [
     {
      "entity_type": "location",
      "id": "the-central-room",
      "name": "The Central Room",
      "field": "location"
     },
     {
      "entity_type": "character",
      "id": "kael",
      "name": "Kael",
      "field": "character_scene"
     },
     {
      "entity_type": "location",
      "id": "the-central-room",
      "name": "The Central Room",
      "field": "location_scene"
     },
     {
      "entity_type": "plot",
      "id": "the-resistance",
      "name": "The Resistance",
      "field": "plot_climax"
     }
    ]
   },
   "returned": {
    "children": [
     {
      "type": "scene_beats",
      "id": "central-room-night-beats",
      "name": "central-room-night-beats"
     }
    ],
    "relations": 0,
    "sections": 8,
    "referenced_by": [
     {
      "entity_type": "relationship",
      "id": "kael-mira",
      "name": "Kael & Mira",
      "field": ""
     },
     {
      "entity_type": "relationship",
      "id": "mira-the-administrator",
      "name": "Mira & The Administrator",
      "field": ""
     }
    ]
   }
  },
  "purge": {
   "items": [
    {
     "id": "central-room-night",
     "type": "scene",
     "name": "Central Room - Night",
     "label": "Scene"
    },
    {
     "id": "central-room-night-beats",
     "type": "scene_beats",
     "name": "central-room-night-beats",
     "label": "Scene Beats"
    }
   ],
   "affected": [
    {
     "entity_type": "relationship",
     "id": "kael-mira",
     "name": "Kael & Mira",
     "field": ""
    },
    {
     "entity_type": "relationship",
     "id": "mira-the-administrator",
     "name": "Mira & The Administrator",
     "field": ""
    }
   ],
   "backup": true,
   "refusal": null
  }
 },
 "world": {
  "entity": {
   "id": "the-i",
   "type": "world",
   "name": "The I",
   "label": "World",
   "deleted_at": "2026-11-23T15:22:08+00:00",
   "one_sentence": "A simulation environment where developing consciousness forms.",
   "has_script": false,
   "fields": {
    "name": "The I",
    "one_sentence": "A simulation environment where developing consciousness forms.",
    "status": "",
    "order_key": 0.0,
    "parent": null,
    "location": null
   },
   "extra": {
    "period": "+400y after the collapse",
    "power": [
     "The Administrator sanctions all decisions",
     "The system enforces compliance automatically"
    ],
    "rules": [
     "The children cannot leave",
     "The Administrator controls all systems"
    ],
    "values": [
     "Preservation over freedom",
     "Stability is sacred"
    ]
   }
  },
  "includes": [
   {
    "id": "the-central-room",
    "entity_type": "location",
    "name": "The Central Room",
    "type": "location",
    "label": "Location"
   },
   {
    "id": "the-garden",
    "entity_type": "location",
    "name": "The Garden",
    "type": "location",
    "label": "Location"
   }
  ],
  "sections": {
   "Conflict": "The I is stable but stagnant. Nothing truly changes — the same meals, the same lessons, the same rooms. The children are safe but not free. And the system that sustains them is beginning to fail in ways the Administrator cannot hide. The central tension: is survival without growth still survival?",
   "Description": "The I — short for \"the Institute,\" though the children don't know that. A vast, enclosed world of rooms, corridors, and simulated spaces. The architecture is clean, functional, slightly too perfect. Meals appear when hunger strikes. Light arrives at the correct angle. Everything works — which is exactly what makes Kael suspicious.",
   "History": "Built four hundred years ago as humanity's last hope. When the outside world became uninhabitable, the Institute's scientists launched Project Save the Children: preserving developing consciousness in a simulated environment, growing new minds to inherit what the old world had lost. The scientists sealed themselves out. The children were meant to be the future.",
   "Livelihood": "The children are sustained entirely by the system. Food, education, recreation — all generated and controlled. There is no work in the traditional sense, no economy, no barter. The children's \"purpose\" is to develop, to learn, to eventually become the inheritors of a world they've never seen.",
   "Notes": "[placeholder — world/Notes]",
   "Power": "The Administrator holds absolute control. Every door, every meal, every lesson flows through its governance. The system's architecture is designed to be invisible — the children obey not because they're forced, but because the alternative doesn't exist. The Administrator enforces order through system constraints, not violence.",
   "Rituals": "Daily lessons in the Central Room. Weekly \"evaluation sessions\" where the Administrator assesses development. The annual \"Harvest Day\" — a celebration of growth metrics, though the children don't know what's being harvested.",
   "Values": "What the Institute holds sacred above all: preservation. Not individual preservation, but the continuation of the species. The children are vessels, not people — though the Administrator would never say that aloud. Growth is measured in compliance, stability, adherence to protocol."
  },
  "relations": {
   "out": [],
   "in": [
    {
     "id": "the-real-world",
     "entity_type": "",
     "name": "the-real-world",
     "kind": "world_variant",
     "note": "",
     "live": true
    }
   ],
   "all": [
    {
     "id": "the-real-world",
     "entity_type": "",
     "name": "the-real-world",
     "kind": "world_variant",
     "note": "",
     "live": true
    }
   ]
  },
  "referenced_by": [],
  "restore": {
   "blockers": [],
   "warnings": {},
   "returned": {
    "children": [
     {
      "type": "location",
      "id": "the-central-room",
      "name": "The Central Room"
     },
     {
      "type": "location",
      "id": "the-garden",
      "name": "The Garden"
     }
    ],
    "relations": 0,
    "sections": 8,
    "referenced_by": []
   }
  },
  "purge": {
   "items": [
    {
     "id": "the-i",
     "type": "world",
     "name": "The I",
     "label": "World"
    },
    {
     "id": "the-central-room",
     "type": "location",
     "name": "The Central Room",
     "label": "Location"
    },
    {
     "id": "the-garden",
     "type": "location",
     "name": "The Garden",
     "label": "Location"
    }
   ],
   "affected": [
    {
     "entity_type": "scene",
     "id": "the-core-day",
     "name": "The Core - Day",
     "field": ""
    },
    {
     "entity_type": "scene",
     "id": "the-core-day",
     "name": "The Core - Day",
     "field": "location"
    }
   ],
   "backup": true,
   "refusal": null
  }
 },
 "character": {
  "entity": {
   "id": "kael",
   "type": "character",
   "name": "Kael",
   "label": "Character",
   "deleted_at": "2026-11-21T18:02:00+00:00",
   "one_sentence": "A young person inside The I who begins to feel the system is wrong.",
   "has_script": false,
   "fields": {
    "name": "Kael",
    "one_sentence": "A young person inside The I who begins to feel the system is wrong.",
    "status": "",
    "order_key": 0.0,
    "parent": null,
    "location": null
   },
   "extra": {
    "story_role": "Protagonist"
   }
  },
  "includes": [],
  "sections": {
   "Arc": "From passive observer to active questioner. Kael begins by trying to fix what's wrong inside the system, and ends by stepping outside it entirely — losing every certainty they ever had.",
   "Background": "Born inside The I. Never known another world. Raised in the standard curriculum with standard expectations. The only unusual thing about Kael is the persistent, nagging sense that something is off — a wrongness that has no name.",
   "Contradictions": "[placeholder — character/Contradictions]",
   "Desires": "[placeholder — character/Desires]",
   "Identity": "[placeholder — character/Identity]",
   "Notes": "[placeholder — character/Notes]",
   "Psychology": "[placeholder — character/Psychology]",
   "Relationships": "- **Mira** — closest friend. Kael trusts her feelings more than their own logic. Fears losing her more than failing the mission.\n- **The Administrator** — antagonist. Kael doesn't hate them; they pity them. Which is worse.",
   "Voice": "Sparse, deliberate. Kael speaks in questions more than statements. When they do commit to words, they land with uncomfortable precision. Avoids contractions — their speech has a formal, slightly archaic quality that other children find odd."
  },
  "relations": {
   "out": [
    {
     "id": "central-room-day",
     "entity_type": "",
     "name": "central-room-day",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "central-room-night",
     "entity_type": "",
     "name": "central-room-night",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-core-day",
     "entity_type": "",
     "name": "the-core-day",
     "kind": "character_scene",
     "note": "",
     "live": true
    }
   ],
   "in": [],
   "all": [
    {
     "id": "central-room-day",
     "entity_type": "",
     "name": "central-room-day",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "central-room-night",
     "entity_type": "",
     "name": "central-room-night",
     "kind": "character_scene",
     "note": "",
     "live": false
    },
    {
     "id": "the-core-day",
     "entity_type": "",
     "name": "the-core-day",
     "kind": "character_scene",
     "note": "",
     "live": true
    }
   ]
  },
  "referenced_by": [
   {
    "entity_type": "relationship",
    "id": "kael-mira",
    "name": "Kael & Mira",
    "field": ""
   },
   {
    "entity_type": "relationship",
    "id": "kael-the-administrator",
    "name": "Kael & The Administrator",
    "field": ""
   }
  ],
  "restore": {
   "blockers": [],
   "warnings": {
    "reference_in_trash": [
     {
      "entity_type": "scene",
      "id": "central-room-day",
      "name": "Central Room - Day",
      "field": "character_scene"
     },
     {
      "entity_type": "scene",
      "id": "central-room-night",
      "name": "Central Room - Night",
      "field": "character_scene"
     }
    ]
   },
   "returned": {
    "children": [],
    "relations": 0,
    "sections": 9,
    "referenced_by": [
     {
      "entity_type": "relationship",
      "id": "kael-mira",
      "name": "Kael & Mira",
      "field": ""
     },
     {
      "entity_type": "relationship",
      "id": "kael-the-administrator",
      "name": "Kael & The Administrator",
      "field": ""
     }
    ]
   }
  },
  "purge": {
   "items": [
    {
     "id": "kael",
     "type": "character",
     "name": "Kael",
     "label": "Character"
    }
   ],
   "affected": [
    {
     "entity_type": "relationship",
     "id": "kael-mira",
     "name": "Kael & Mira",
     "field": ""
    },
    {
     "entity_type": "relationship",
     "id": "kael-the-administrator",
     "name": "Kael & The Administrator",
     "field": ""
    }
   ],
   "backup": true,
   "refusal": null
  }
 },
 "details": {
  "the-i": {
   "entity": {
    "id": "the-i",
    "type": "world",
    "name": "The I",
    "label": "World",
    "deleted_at": "2026-11-23T15:22:08+00:00",
    "one_sentence": "A simulation environment where developing consciousness forms.",
    "has_script": false,
    "fields": {
     "name": "The I",
     "one_sentence": "A simulation environment where developing consciousness forms.",
     "status": "",
     "order_key": 0.0,
     "parent": null,
     "location": null
    },
    "extra": {
     "period": "+400y after the collapse",
     "power": [
      "The Administrator sanctions all decisions",
      "The system enforces compliance automatically"
     ],
     "rules": [
      "The children cannot leave",
      "The Administrator controls all systems"
     ],
     "values": [
      "Preservation over freedom",
      "Stability is sacred"
     ]
    }
   },
   "includes": [
    {
     "id": "the-central-room",
     "entity_type": "location",
     "name": "The Central Room",
     "type": "location",
     "label": "Location"
    },
    {
     "id": "the-garden",
     "entity_type": "location",
     "name": "The Garden",
     "type": "location",
     "label": "Location"
    }
   ],
   "sections": {
    "Conflict": "The I is stable but stagnant. Nothing truly changes — the same meals, the same lessons, the same rooms. The children are safe but not free. And the system that sustains them is beginning to fail in ways the Administrator cannot hide. The central tension: is survival without growth still survival?",
    "Description": "The I — short for \"the Institute,\" though the children don't know that. A vast, enclosed world of rooms, corridors, and simulated spaces. The architecture is clean, functional, slightly too perfect. Meals appear when hunger strikes. Light arrives at the correct angle. Everything works — which is exactly what makes Kael suspicious.",
    "History": "Built four hundred years ago as humanity's last hope. When the outside world became uninhabitable, the Institute's scientists launched Project Save the Children: preserving developing consciousness in a simulated environment, growing new minds to inherit what the old world had lost. The scientists sealed themselves out. The children were meant to be the future.",
    "Livelihood": "The children are sustained entirely by the system. Food, education, recreation — all generated and controlled. There is no work in the traditional sense, no economy, no barter. The children's \"purpose\" is to develop, to learn, to eventually become the inheritors of a world they've never seen.",
    "Notes": "[placeholder — world/Notes]",
    "Power": "The Administrator holds absolute control. Every door, every meal, every lesson flows through its governance. The system's architecture is designed to be invisible — the children obey not because they're forced, but because the alternative doesn't exist. The Administrator enforces order through system constraints, not violence.",
    "Rituals": "Daily lessons in the Central Room. Weekly \"evaluation sessions\" where the Administrator assesses development. The annual \"Harvest Day\" — a celebration of growth metrics, though the children don't know what's being harvested.",
    "Values": "What the Institute holds sacred above all: preservation. Not individual preservation, but the continuation of the species. The children are vessels, not people — though the Administrator would never say that aloud. Growth is measured in compliance, stability, adherence to protocol."
   },
   "relations": {
    "out": [],
    "in": [
     {
      "id": "the-real-world",
      "entity_type": "",
      "name": "the-real-world",
      "kind": "world_variant",
      "note": "",
      "live": true
     }
    ],
    "all": [
     {
      "id": "the-real-world",
      "entity_type": "",
      "name": "the-real-world",
      "kind": "world_variant",
      "note": "",
      "live": true
     }
    ]
   },
   "referenced_by": [],
   "restore": {
    "blockers": [],
    "warnings": {},
    "returned": {
     "children": [
      {
       "type": "location",
       "id": "the-central-room",
       "name": "The Central Room"
      },
      {
       "type": "location",
       "id": "the-garden",
       "name": "The Garden"
      }
     ],
     "relations": 0,
     "sections": 8,
     "referenced_by": []
    }
   },
   "purge": {
    "items": [
     {
      "id": "the-i",
      "type": "world",
      "name": "The I",
      "label": "World"
     },
     {
      "id": "the-central-room",
      "type": "location",
      "name": "The Central Room",
      "label": "Location"
     },
     {
      "id": "the-garden",
      "type": "location",
      "name": "The Garden",
      "label": "Location"
     }
    ],
    "affected": [
     {
      "entity_type": "scene",
      "id": "the-core-day",
      "name": "The Core - Day",
      "field": ""
     },
     {
      "entity_type": "scene",
      "id": "the-core-day",
      "name": "The Core - Day",
      "field": "location"
     }
    ],
    "backup": true,
    "refusal": null
   }
  },
  "central-room-day": {
   "entity": {
    "id": "central-room-day",
    "type": "scene",
    "name": "Central Room - Day",
    "label": "Scene",
    "deleted_at": "2026-11-22T10:05:00+00:00",
    "one_sentence": "",
    "has_script": true,
    "fields": {
     "name": "Central Room - Day",
     "one_sentence": "",
     "status": "drafted",
     "order_key": 1.0,
     "parent": {
      "id": "seq-discovery",
      "entity_type": "sequence",
      "name": "The Discovery"
     },
     "location": {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room"
     }
    },
    "extra": {
     "act_id": "act-1",
     "dramatic_role": "plot_role",
     "int_ext": "INT.",
     "time_of_day": "DAY",
     "type": "scene",
     "value_turns": [
      {
       "plot": "the-resistance",
       "value": "freedom",
       "from": "imprisoned",
       "to": "free",
       "effects": [
        {
         "character": "kael",
         "levels": [
          {
           "conflict_level": "inner",
           "effect": "Kael realises the lock was never engaged, and his own acceptance of it was the cage."
          },
          {
           "conflict_level": "personal",
           "effect": "Kael's hand on the handle is a public refusal to stay."
          }
         ]
        },
        {
         "character": "mira",
         "levels": [
          {
           "conflict_level": "extra-personal",
           "effect": "The system that holds the children is shown, for the first time, to be only a story they were told."
          }
         ]
        }
       ]
      },
      {
       "plot": "the-resistance",
       "value": "trust",
       "from": "deceived",
       "to": "open",
       "effects": [
        {
         "character": "kael",
         "levels": [
          {
           "conflict_level": "inner",
           "effect": "Every guard Kael had been told about is a lie; he can no longer tell which of his beliefs is his own."
          },
          {
           "conflict_level": "personal",
           "effect": "The Institute's authority over Kael collapses with the lock."
          }
         ]
        }
       ]
      }
     ]
    }
   },
   "includes": [],
   "sections": {
    "Beats": "",
    "Conflict": "",
    "Content": "KAEL stands before the door, hand on the handle. It turns. The lock was never engaged.",
    "Dramatic Function": "The inciting incident. Kael's private doubt becomes public action.",
    "Notes": "This scene establishes the central metaphor: the door that was always open.",
    "Objective": "[placeholder — scene/Objective]",
    "Production": "[placeholder — scene/Production]",
    "Value Turn": "[placeholder — scene/Value Turn]"
   },
   "relations": {
    "out": [],
    "in": [
     {
      "id": "kael",
      "entity_type": "",
      "name": "kael",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "mira",
      "entity_type": "",
      "name": "mira",
      "kind": "character_scene",
      "note": "",
      "live": true
     },
     {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room",
      "kind": "location_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-resistance",
      "entity_type": "",
      "name": "the-resistance",
      "kind": "plot_inciting_incident",
      "note": "Kael discovers the door isn't locked — it was never locked.",
      "live": false
     },
     {
      "id": "the-scientists-last-stand",
      "entity_type": "",
      "name": "the-scientists-last-stand",
      "kind": "plot_setup",
      "note": "The scientists built the Institute to protect the children.",
      "live": true
     }
    ],
    "all": [
     {
      "id": "kael",
      "entity_type": "",
      "name": "kael",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "mira",
      "entity_type": "",
      "name": "mira",
      "kind": "character_scene",
      "note": "",
      "live": true
     },
     {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room",
      "kind": "location_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-resistance",
      "entity_type": "",
      "name": "the-resistance",
      "kind": "plot_inciting_incident",
      "note": "Kael discovers the door isn't locked — it was never locked.",
      "live": false
     },
     {
      "id": "the-scientists-last-stand",
      "entity_type": "",
      "name": "the-scientists-last-stand",
      "kind": "plot_setup",
      "note": "The scientists built the Institute to protect the children.",
      "live": true
     }
    ]
   },
   "referenced_by": [
    {
     "entity_type": "relationship",
     "id": "kael-mira",
     "name": "Kael & Mira",
     "field": ""
    },
    {
     "entity_type": "relationship",
     "id": "kael-the-administrator",
     "name": "Kael & The Administrator",
     "field": ""
    }
   ],
   "restore": {
    "blockers": [],
    "warnings": {
     "reference_in_trash": [
      {
       "entity_type": "location",
       "id": "the-central-room",
       "name": "The Central Room",
       "field": "location"
      },
      {
       "entity_type": "character",
       "id": "kael",
       "name": "Kael",
       "field": "character_scene"
      },
      {
       "entity_type": "location",
       "id": "the-central-room",
       "name": "The Central Room",
       "field": "location_scene"
      },
      {
       "entity_type": "plot",
       "id": "the-resistance",
       "name": "The Resistance",
       "field": "plot_inciting_incident"
      }
     ],
     "stranded_children": [
      {
       "entity_type": "scene_beats",
       "id": "central-room-day-beats",
       "field": "parent",
       "name": "central-room-day-beats"
      }
     ]
    },
    "returned": {
     "children": [],
     "relations": 0,
     "sections": 8,
     "referenced_by": [
      {
       "entity_type": "relationship",
       "id": "kael-mira",
       "name": "Kael & Mira",
       "field": ""
      },
      {
       "entity_type": "relationship",
       "id": "kael-the-administrator",
       "name": "Kael & The Administrator",
       "field": ""
      }
     ]
    }
   },
   "purge": {
    "items": [
     {
      "id": "central-room-day",
      "type": "scene",
      "name": "Central Room - Day",
      "label": "Scene"
     }
    ],
    "affected": [
     {
      "entity_type": "relationship",
      "id": "kael-mira",
      "name": "Kael & Mira",
      "field": ""
     },
     {
      "entity_type": "relationship",
      "id": "kael-the-administrator",
      "name": "Kael & The Administrator",
      "field": ""
     }
    ],
    "backup": true,
    "refusal": null
   }
  },
  "kael": {
   "entity": {
    "id": "kael",
    "type": "character",
    "name": "Kael",
    "label": "Character",
    "deleted_at": "2026-11-21T18:02:00+00:00",
    "one_sentence": "A young person inside The I who begins to feel the system is wrong.",
    "has_script": false,
    "fields": {
     "name": "Kael",
     "one_sentence": "A young person inside The I who begins to feel the system is wrong.",
     "status": "",
     "order_key": 0.0,
     "parent": null,
     "location": null
    },
    "extra": {
     "story_role": "Protagonist"
    }
   },
   "includes": [],
   "sections": {
    "Arc": "From passive observer to active questioner. Kael begins by trying to fix what's wrong inside the system, and ends by stepping outside it entirely — losing every certainty they ever had.",
    "Background": "Born inside The I. Never known another world. Raised in the standard curriculum with standard expectations. The only unusual thing about Kael is the persistent, nagging sense that something is off — a wrongness that has no name.",
    "Contradictions": "[placeholder — character/Contradictions]",
    "Desires": "[placeholder — character/Desires]",
    "Identity": "[placeholder — character/Identity]",
    "Notes": "[placeholder — character/Notes]",
    "Psychology": "[placeholder — character/Psychology]",
    "Relationships": "- **Mira** — closest friend. Kael trusts her feelings more than their own logic. Fears losing her more than failing the mission.\n- **The Administrator** — antagonist. Kael doesn't hate them; they pity them. Which is worse.",
    "Voice": "Sparse, deliberate. Kael speaks in questions more than statements. When they do commit to words, they land with uncomfortable precision. Avoids contractions — their speech has a formal, slightly archaic quality that other children find odd."
   },
   "relations": {
    "out": [
     {
      "id": "central-room-day",
      "entity_type": "",
      "name": "central-room-day",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "central-room-night",
      "entity_type": "",
      "name": "central-room-night",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-core-day",
      "entity_type": "",
      "name": "the-core-day",
      "kind": "character_scene",
      "note": "",
      "live": true
     }
    ],
    "in": [],
    "all": [
     {
      "id": "central-room-day",
      "entity_type": "",
      "name": "central-room-day",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "central-room-night",
      "entity_type": "",
      "name": "central-room-night",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-core-day",
      "entity_type": "",
      "name": "the-core-day",
      "kind": "character_scene",
      "note": "",
      "live": true
     }
    ]
   },
   "referenced_by": [
    {
     "entity_type": "relationship",
     "id": "kael-mira",
     "name": "Kael & Mira",
     "field": ""
    },
    {
     "entity_type": "relationship",
     "id": "kael-the-administrator",
     "name": "Kael & The Administrator",
     "field": ""
    }
   ],
   "restore": {
    "blockers": [],
    "warnings": {
     "reference_in_trash": [
      {
       "entity_type": "scene",
       "id": "central-room-day",
       "name": "Central Room - Day",
       "field": "character_scene"
      },
      {
       "entity_type": "scene",
       "id": "central-room-night",
       "name": "Central Room - Night",
       "field": "character_scene"
      }
     ]
    },
    "returned": {
     "children": [],
     "relations": 0,
     "sections": 9,
     "referenced_by": [
      {
       "entity_type": "relationship",
       "id": "kael-mira",
       "name": "Kael & Mira",
       "field": ""
      },
      {
       "entity_type": "relationship",
       "id": "kael-the-administrator",
       "name": "Kael & The Administrator",
       "field": ""
      }
     ]
    }
   },
   "purge": {
    "items": [
     {
      "id": "kael",
      "type": "character",
      "name": "Kael",
      "label": "Character"
     }
    ],
    "affected": [
     {
      "entity_type": "relationship",
      "id": "kael-mira",
      "name": "Kael & Mira",
      "field": ""
     },
     {
      "entity_type": "relationship",
      "id": "kael-the-administrator",
      "name": "Kael & The Administrator",
      "field": ""
     }
    ],
    "backup": true,
    "refusal": null
   }
  },
  "central-room-night": {
   "entity": {
    "id": "central-room-night",
    "type": "scene",
    "name": "Central Room - Night",
    "label": "Scene",
    "deleted_at": "2026-11-20T09:15:00+00:00",
    "one_sentence": "",
    "has_script": true,
    "fields": {
     "name": "Central Room - Night",
     "one_sentence": "",
     "status": "drafted",
     "order_key": 2.0,
     "parent": {
      "id": "seq-discovery",
      "entity_type": "sequence",
      "name": "The Discovery"
     },
     "location": {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room"
     }
    },
    "extra": {
     "act_id": "act-1",
     "dramatic_role": "plot_role",
     "int_ext": "INT.",
     "time_of_day": "NIGHT",
     "type": "scene",
     "value_turns": [
      {
       "plot": "the-resistance",
       "value": "freedom",
       "from": "free",
       "to": "free",
       "effects": [
        {
         "character": "kael",
         "levels": [
          {
           "conflict_level": "inner",
           "effect": "Refusing the offer is the deepening: the change is in how the choice lands, not in the state — freedom now has a cost attached to it."
          },
          {
           "conflict_level": "personal",
           "effect": "The offer makes the known world real again by putting a price on leaving it."
          }
         ]
        },
        {
         "character": "mira",
         "levels": [
          {
           "conflict_level": "inner",
           "effect": "Mira, unseen in the room, is given the same choice and must answer it alone."
          }
         ]
        }
       ]
      },
      {
       "plot": "the-resistance",
       "value": "trust",
       "from": "open",
       "to": "open",
       "effects": [
        {
         "character": "kael",
         "levels": [
          {
           "conflict_level": "inner",
           "effect": "The Administrator speaks with a reasonable voice, so Kael's judgement of it has to become his own rather than borrowed."
          }
         ]
        }
       ]
      }
     ]
    }
   },
   "includes": [
    {
     "id": "central-room-night-beats",
     "entity_type": "scene_beats",
     "name": "central-room-night-beats",
     "type": "scene_beats",
     "label": "Scene Beats"
    }
   ],
   "sections": {
    "Beats": "",
    "Conflict": "",
    "Content": "The ADMINISTRATOR speaks from everywhere and nowhere. Kael listens. Then shakes their head.",
    "Dramatic Function": "The sequence climax. Kael chooses the unknown over the known.",
    "Notes": "The Administrator's voice is calm, reasonable, and utterly alien.",
    "Objective": "[placeholder — scene/Objective]",
    "Production": "[placeholder — scene/Production]",
    "Value Turn": "[placeholder — scene/Value Turn]"
   },
   "relations": {
    "out": [],
    "in": [
     {
      "id": "kael",
      "entity_type": "",
      "name": "kael",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room",
      "kind": "location_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-resistance",
      "entity_type": "",
      "name": "the-resistance",
      "kind": "plot_climax",
      "note": "The Administrator makes its final offer. Kael refuses.",
      "live": false
     }
    ],
    "all": [
     {
      "id": "kael",
      "entity_type": "",
      "name": "kael",
      "kind": "character_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-central-room",
      "entity_type": "location",
      "name": "The Central Room",
      "kind": "location_scene",
      "note": "",
      "live": false
     },
     {
      "id": "the-resistance",
      "entity_type": "",
      "name": "the-resistance",
      "kind": "plot_climax",
      "note": "The Administrator makes its final offer. Kael refuses.",
      "live": false
     }
    ]
   },
   "referenced_by": [
    {
     "entity_type": "relationship",
     "id": "kael-mira",
     "name": "Kael & Mira",
     "field": ""
    },
    {
     "entity_type": "relationship",
     "id": "mira-the-administrator",
     "name": "Mira & The Administrator",
     "field": ""
    }
   ],
   "restore": {
    "blockers": [],
    "warnings": {
     "reference_in_trash": [
      {
       "entity_type": "location",
       "id": "the-central-room",
       "name": "The Central Room",
       "field": "location"
      },
      {
       "entity_type": "character",
       "id": "kael",
       "name": "Kael",
       "field": "character_scene"
      },
      {
       "entity_type": "location",
       "id": "the-central-room",
       "name": "The Central Room",
       "field": "location_scene"
      },
      {
       "entity_type": "plot",
       "id": "the-resistance",
       "name": "The Resistance",
       "field": "plot_climax"
      }
     ]
    },
    "returned": {
     "children": [
      {
       "type": "scene_beats",
       "id": "central-room-night-beats",
       "name": "central-room-night-beats"
      }
     ],
     "relations": 0,
     "sections": 8,
     "referenced_by": [
      {
       "entity_type": "relationship",
       "id": "kael-mira",
       "name": "Kael & Mira",
       "field": ""
      },
      {
       "entity_type": "relationship",
       "id": "mira-the-administrator",
       "name": "Mira & The Administrator",
       "field": ""
      }
     ]
    }
   },
   "purge": {
    "items": [
     {
      "id": "central-room-night",
      "type": "scene",
      "name": "Central Room - Night",
      "label": "Scene"
     },
     {
      "id": "central-room-night-beats",
      "type": "scene_beats",
      "name": "central-room-night-beats",
      "label": "Scene Beats"
     }
    ],
    "affected": [
     {
      "entity_type": "relationship",
      "id": "kael-mira",
      "name": "Kael & Mira",
      "field": ""
     },
     {
      "entity_type": "relationship",
      "id": "mira-the-administrator",
      "name": "Mira & The Administrator",
      "field": ""
     }
    ],
    "backup": true,
    "refusal": null
   }
  },
  "central-room-day-beats": {
   "entity": {
    "id": "central-room-day-beats",
    "type": "scene_beats",
    "name": "central-room-day-beats",
    "label": "Scene Beats",
    "deleted_at": "2026-11-14T21:40:00+00:00",
    "one_sentence": "",
    "has_script": false,
    "fields": {
     "name": "",
     "one_sentence": "",
     "status": "",
     "order_key": 0.0,
     "parent": {
      "id": "central-room-day",
      "entity_type": "scene",
      "name": "Central Room - Day"
     },
     "location": null
    },
    "extra": {
     "type": "scene_beats",
     "driver": "kael",
     "scene_objective": "Find out whether the door was ever locked.",
     "turning_point": "The handle turns. The lock was never engaged.",
     "true_character": [
      {
       "character": "kael",
       "dilemma": "Open the door and become the one who broke it, or leave it shut and stay innocent of it.",
       "choice_reveals": "He needs the truth more than he needs to be innocent of it."
      }
     ],
     "changes": [
      {
       "entity": "kael",
       "change": "No longer believes the door was locked; suspects the story he was told was the lock."
      },
      {
       "entity": "the-central-room",
       "change": "Stops being a boundary and becomes an exit."
      }
     ],
     "beats": [
      {
       "action": {
        "by": "kael",
        "surface": "Hand flat on the door",
        "subtext": "testing whether it will hold"
       },
       "reaction": {
        "by": "kael",
        "surface": "It turns",
        "subtext": "discovering his own prison was agreed, not built"
       },
       "gap": "He expected resistance and got none."
      },
      {
       "action": {
        "by": "the-central-room",
        "surface": "The room beyond is lit",
        "subtext": "offering a version of home back to him"
       },
       "reaction": {
        "by": "kael",
        "surface": "He steps back",
        "subtext": "refusing the bargain the room is making"
       }
      }
     ]
    }
   },
   "includes": [],
   "sections": {
    "Notes": "The lock is the scene's whole mechanism: the door was never locked, so the\ncage was agreement. The gap opens in the first beat — action and reaction\nboth Kael, which is why the exchange draws it as inner conflict — and the\nsecond beat puts the room itself on a lane, so the circumstance is a\nparticipant rather than scenery."
   },
   "relations": {
    "out": [],
    "in": [],
    "all": []
   },
   "referenced_by": [],
   "restore": {
    "blockers": [
     {
      "code": "parent_trashed",
      "message": "“Central Room - Day” is still in the trash. Restore it too, or this comes back where nothing can see it.",
      "fix": {
       "entity_type": "scene",
       "id": "central-room-day",
       "name": "Central Room - Day"
      }
     }
    ],
    "warnings": {},
    "returned": {
     "children": [],
     "relations": 0,
     "sections": 1,
     "referenced_by": []
    }
   },
   "purge": {
    "items": [
     {
      "id": "central-room-day-beats",
      "type": "scene_beats",
      "name": "central-room-day-beats",
      "label": "Scene Beats"
     }
    ],
    "affected": [],
    "backup": true,
    "refusal": null
   }
  },
  "the-resistance": {
   "entity": {
    "id": "the-resistance",
    "type": "plot",
    "name": "The Resistance",
    "label": "Plot",
    "deleted_at": "2026-09-21T08:00:00+00:00",
    "one_sentence": "Kael and Mira organize the children to breach the Central Room.",
    "has_script": false,
    "fields": {
     "name": "The Resistance",
     "one_sentence": "Kael and Mira organize the children to breach the Central Room.",
     "status": "active",
     "order_key": 0.0,
     "parent": null,
     "location": null
    },
    "extra": {
     "characters": [
      "kael",
      "mira"
     ],
     "plot_scope": "main",
     "plot_type": "Setup"
    }
   },
   "includes": [],
   "sections": {
    "Characters": "[placeholder — plot/Characters]",
    "Notes": "[placeholder — plot/Notes]",
    "Role": "[placeholder — plot/Role]",
    "Summary": "Kael's growing awareness of the system's wrongness becomes a quiet revolution. What begins as private questions becomes shared doubt, and shared doubt becomes organized resistance. The children must decide: accept the world as it is, or risk everything to find what's beyond the door.",
    "Threads": "[placeholder — plot/Threads]",
    "Value": "[placeholder — plot/Value]"
   },
   "relations": {
    "out": [
     {
      "id": "central-room-night",
      "entity_type": "",
      "name": "central-room-night",
      "kind": "plot_climax",
      "note": "The Administrator makes its final offer. Kael refuses.",
      "live": false
     },
     {
      "id": "central-room-day",
      "entity_type": "",
      "name": "central-room-day",
      "kind": "plot_inciting_incident",
      "note": "Kael discovers the door isn't locked — it was never locked.",
      "live": false
     },
     {
      "id": "the-core-day",
      "entity_type": "",
      "name": "the-core-day",
      "kind": "plot_resolution",
      "note": "The children emerge into the real world for the first time.",
      "live": true
     }
    ],
    "in": [],
    "all": [
     {
      "id": "central-room-night",
      "entity_type": "",
      "name": "central-room-night",
      "kind": "plot_climax",
      "note": "The Administrator makes its final offer. Kael refuses.",
      "live": false
     },
     {
      "id": "central-room-day",
      "entity_type": "",
      "name": "central-room-day",
      "kind": "plot_inciting_incident",
      "note": "Kael discovers the door isn't locked — it was never locked.",
      "live": false
     },
     {
      "id": "the-core-day",
      "entity_type": "",
      "name": "the-core-day",
      "kind": "plot_resolution",
      "note": "The children emerge into the real world for the first time.",
      "live": true
     }
    ]
   },
   "referenced_by": [],
   "restore": {
    "blockers": [],
    "warnings": {
     "reference_in_trash": [
      {
       "entity_type": "scene",
       "id": "central-room-night",
       "name": "Central Room - Night",
       "field": "plot_climax"
      },
      {
       "entity_type": "scene",
       "id": "central-room-day",
       "name": "Central Room - Day",
       "field": "plot_inciting_incident"
      },
      {
       "entity_type": "character",
       "id": "kael",
       "name": "Kael",
       "field": "characters"
      }
     ]
    },
    "returned": {
     "children": [],
     "relations": 0,
     "sections": 6,
     "referenced_by": []
    }
   },
   "purge": {
    "items": [
     {
      "id": "the-resistance",
      "type": "plot",
      "name": "The Resistance",
      "label": "Plot"
     }
    ],
    "affected": [],
    "backup": true,
    "refusal": null
   }
  }
 },
 "purgePreview": {
  "items": [
   {
    "id": "kael",
    "type": "character",
    "name": "Kael",
    "label": "Character"
   },
   {
    "id": "central-room-night",
    "type": "scene",
    "name": "Central Room - Night",
    "label": "Scene"
   },
   {
    "id": "central-room-night-beats",
    "type": "scene_beats",
    "name": "central-room-night-beats",
    "label": "Scene Beats"
   }
  ],
  "affected": [
   {
    "entity_type": "relationship",
    "id": "kael-mira",
    "name": "Kael & Mira",
    "field": ""
   },
   {
    "entity_type": "relationship",
    "id": "kael-the-administrator",
    "name": "Kael & The Administrator",
    "field": ""
   },
   {
    "entity_type": "relationship",
    "id": "mira-the-administrator",
    "name": "Mira & The Administrator",
    "field": ""
   }
  ],
  "backup": true,
  "refusal": null
 }
};
