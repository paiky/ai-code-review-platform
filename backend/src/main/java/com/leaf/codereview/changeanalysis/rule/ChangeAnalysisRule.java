package com.leaf.codereview.changeanalysis.rule;

import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.domain.RuleMatch;

import java.util.Optional;

public interface ChangeAnalysisRule {

    String code();

    Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText);
}