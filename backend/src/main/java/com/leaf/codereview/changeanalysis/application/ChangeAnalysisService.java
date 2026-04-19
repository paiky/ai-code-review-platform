package com.leaf.codereview.changeanalysis.application;

import com.leaf.codereview.changeanalysis.domain.AnalyzedFile;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangeEvidence;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.domain.FileChangeType;
import com.leaf.codereview.changeanalysis.domain.ImpactedResource;
import com.leaf.codereview.changeanalysis.domain.RuleMatch;
import com.leaf.codereview.changeanalysis.rule.ChangeAnalysisRule;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class ChangeAnalysisService {

    private final List<ChangeAnalysisRule> rules;

    public ChangeAnalysisService(List<ChangeAnalysisRule> rules) {
        this.rules = rules == null ? List.of() : List.copyOf(rules);
    }

    public ChangeAnalysisResult analyze(ChangeAnalysisRequest request) {
        List<ChangedFile> inputFiles = normalizeFiles(request);
        Set<ChangeType> allChangeTypes = new LinkedHashSet<>();
        List<ImpactedResource> impactedResources = new ArrayList<>();
        List<ChangeEvidence> evidences = new ArrayList<>();
        Map<String, Set<ChangeType>> fileMatches = new LinkedHashMap<>();

        for (ChangedFile file : inputFiles) {
            fileMatches.putIfAbsent(file.effectivePath(), EnumSet.noneOf(ChangeType.class));
            for (ChangeAnalysisRule rule : rules) {
                rule.analyze(file, request.diffText()).ifPresent(match -> applyMatch(match, allChangeTypes, impactedResources, evidences, fileMatches));
            }
        }

        List<AnalyzedFile> analyzedFiles = inputFiles.stream()
                .map(file -> new AnalyzedFile(file.effectivePath(), file.changeType(), fileMatches.getOrDefault(file.effectivePath(), Set.of())))
                .toList();

        return new ChangeAnalysisResult(
                buildSummary(inputFiles.size(), allChangeTypes),
                inputFiles.size(),
                allChangeTypes,
                analyzedFiles,
                impactedResources,
                evidences
        );
    }

    private void applyMatch(
            RuleMatch match,
            Set<ChangeType> allChangeTypes,
            List<ImpactedResource> impactedResources,
            List<ChangeEvidence> evidences,
            Map<String, Set<ChangeType>> fileMatches
    ) {
        allChangeTypes.add(match.changeType());
        impactedResources.addAll(match.impactedResources());
        evidences.addAll(match.evidences());
        fileMatches.computeIfAbsent(match.changedFile().effectivePath(), ignored -> EnumSet.noneOf(ChangeType.class))
                .add(match.changeType());
    }

    private List<ChangedFile> normalizeFiles(ChangeAnalysisRequest request) {
        if (!request.changedFiles().isEmpty()) {
            return request.changedFiles();
        }
        if (request.diffText() != null && !request.diffText().isBlank()) {
            return List.of(new ChangedFile("__global_diff__", null, "__global_diff__", FileChangeType.UNKNOWN, request.diffText()));
        }
        return List.of();
    }

    private String buildSummary(int changedFileCount, Set<ChangeType> changeTypes) {
        if (changedFileCount == 0) {
            return "No changed files were provided.";
        }
        if (changeTypes.isEmpty()) {
            return "Analyzed " + changedFileCount + " changed file(s); no MVP change type matched.";
        }
        String joinedTypes = changeTypes.stream()
                .sorted(Comparator.comparing(Enum::ordinal))
                .map(Enum::name)
                .collect(Collectors.joining(", "));
        return "Analyzed " + changedFileCount + " changed file(s); matched change types: " + joinedTypes + ".";
    }
}