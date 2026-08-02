import unittest

import samvaad_config


class BuildPromptTests(unittest.TestCase):
    def test_no_vertical_returns_base_instructions_only(self):
        prompt = samvaad_config.build_prompt()
        self.assertEqual(prompt, samvaad_config.INSTRUCTIONS)

    def test_hardware_vertical_appends_the_pack_fragment(self):
        prompt = samvaad_config.build_prompt("hardware", "1.0.0")
        self.assertTrue(prompt.startswith(samvaad_config.INSTRUCTIONS))
        self.assertIn("hardware", prompt.lower())
        self.assertGreater(len(prompt), len(samvaad_config.INSTRUCTIONS))

    def test_unknown_vertical_falls_back_to_base_instructions(self):
        prompt = samvaad_config.build_prompt("nonexistent", "1.0.0")
        self.assertEqual(prompt, samvaad_config.INSTRUCTIONS)

    def test_tool_registry_is_unaffected_by_vertical_choice(self):
        import agent
        before = list(agent.TOOLS.keys()) if isinstance(agent.TOOLS, dict) else list(agent.TOOLS)
        samvaad_config.build_prompt("hardware", "1.0.0")
        after = list(agent.TOOLS.keys()) if isinstance(agent.TOOLS, dict) else list(agent.TOOLS)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
